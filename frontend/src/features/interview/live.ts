import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useState } from 'react'

import { opinionKeys } from './opinions'
import { sessionKeys } from './sessions'
import { api, ApiError, unwrap, type Schemas } from '@/lib/api/client'
import { readEvents, type SseEvent } from '@/lib/api/sse'

export type InterviewAttendance = Schemas['Attendance']
export type SessionProgress = Schemas['SessionProgress']

/** 배정된 면접관의 준비 완료와 현재 접속 현황. */
export function useInterviewAttendance(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: sessionKeys.attendance(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/interviewer/sessions/{stageId}/{applicationId}/attendance', {
          params: { path: { stageId, applicationId } },
        }),
      ),
  })
}

/**
 * [준비 완료]와 그 취소. 두 면접관이 모두 준비 완료하면 서버가 그 자리에서 면접을 시작하므로,
 * 준비 현황과 함께 면접 상태(질문 기록 권한)와 내 면접 목록도 다시 읽는다.
 */
export function useInterviewReady(stageId: string, applicationId: string) {
  const client = useQueryClient()
  const params = { params: { path: { stageId, applicationId } } }
  const onSuccess = (saved: InterviewAttendance) => {
    client.setQueryData(sessionKeys.attendance(stageId, applicationId), saved)
    void client.invalidateQueries({ queryKey: sessionKeys.workspace(stageId, applicationId) })
    void client.invalidateQueries({ queryKey: sessionKeys.mine })
  }
  return {
    ready: useMutation({
      mutationFn: () =>
        unwrap(api.POST('/api/interviewer/sessions/{stageId}/{applicationId}/ready', params)),
      onSuccess,
    }),
    cancel: useMutation({
      mutationFn: () =>
        unwrap(api.DELETE('/api/interviewer/sessions/{stageId}/{applicationId}/ready', params)),
      onSuccess,
    }),
  }
}

/** HR 지원자 목록과 배정 카드에서 같은 전형 진행 현황 캐시를 공유한다. */
export function useStageInterviewProgress(stageId: string, enabled = true) {
  return useQuery({
    queryKey: sessionKeys.progress(stageId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/interview/sessions', {
          params: { path: { stageId } },
        }),
      ),
  })
}

/** 면접관 화면 하나의 연결. 입장, 질문, 상태, 의견을 알림 뒤 권한이 적용된 조회 API로 다시 읽는다. */
export function useInterviewRoomLive(stageId: string, applicationId: string) {
  const client = useQueryClient()
  const open = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        api.GET('/api/interviewer/sessions/{stageId}/{applicationId}/events', {
          params: { path: { stageId, applicationId } },
          parseAs: 'stream',
          signal,
          credentials: 'same-origin',
        }),
      ),
    [stageId, applicationId],
  )
  const refresh = useCallback(() => {
    void client.invalidateQueries({ queryKey: sessionKeys.workspace(stageId, applicationId) })
    void client.invalidateQueries({ queryKey: sessionKeys.attendance(stageId, applicationId) })
    void client.invalidateQueries({ queryKey: opinionKeys.mine(stageId, applicationId) })
    void client.invalidateQueries({ queryKey: sessionKeys.mine })
  }, [client, stageId, applicationId])
  return useInterviewEvents(`room:${stageId}:${applicationId}`, open, refresh)
}

/** HR 화면은 전형마다 연결 하나로 모든 지원자의 면접 변경을 받는다. */
export function useInterviewStageLive(stageId: string, enabled = true) {
  const client = useQueryClient()
  const open = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        api.GET('/api/stages/{stageId}/interview/events', {
          params: { path: { stageId } },
          parseAs: 'stream',
          signal,
          credentials: 'same-origin',
        }),
      ),
    [stageId],
  )
  const refresh = useCallback(
    (event?: SseEvent) => {
      const applicationId = changedApplication(event?.data)
      void client.invalidateQueries({ queryKey: sessionKeys.stageAssignment(stageId) })
      void client.invalidateQueries({ queryKey: sessionKeys.progress(stageId) })
      void client.invalidateQueries({
        queryKey: applicationId
          ? sessionKeys.assignment(stageId, applicationId)
          : ['interview', 'session', stageId],
      })
      void client.invalidateQueries({
        queryKey: applicationId
          ? ['stage', stageId, 'interview', applicationId]
          : ['stage', stageId, 'interview'],
      })
      void client.invalidateQueries({ queryKey: opinionKeys.stage(stageId) })
      void client.invalidateQueries({ queryKey: ['stage', stageId, 'overview'] })
    },
    [client, stageId],
  )
  return useInterviewEvents(`stage:${stageId}`, open, refresh, enabled)
}

/** 알림이 불완전하면 전체 갱신으로 놓친 변경을 회복한다. */
function changedApplication(data: string | undefined): string | undefined {
  if (!data) return undefined
  try {
    const payload: unknown = JSON.parse(data)
    if (
      payload !== null &&
      typeof payload === 'object' &&
      'applicationId' in payload &&
      typeof payload.applicationId === 'string' &&
      payload.applicationId.trim()
    ) {
      return payload.applicationId
    }
  } catch {
    // 잘못된 알림 내용은 화면에 표시하지 않고 전체를 다시 조회한다
  }
  return undefined
}

type OpenStream = (signal: AbortSignal) => Promise<ReadableStream<Uint8Array> | null>

/**
 * 연결이 복구되면 놓친 변경도 다시 읽는다. 서버의 15초 ping이 멎어도 연결을 다시 열고,
 * 화면을 떠나면 요청과 재연결 타이머를 모두 정리한다. 권한 오류에는 재연결하지 않는다.
 */
function useInterviewEvents(
  key: string,
  open: OpenStream,
  refresh: (event?: SseEvent) => void,
  enabled = true,
) {
  const source = useMemo(() => ({ key, enabled }), [key, enabled])
  const [connection, setConnection] = useState<{
    source: typeof source | null
    connected: boolean
  }>({
    source: null,
    connected: false,
  })
  useEffect(() => {
    if (!source.enabled) return
    let stopped = false
    let waiting: AbortController | undefined
    let retry: ReturnType<typeof setTimeout> | undefined
    let heartbeat: ReturnType<typeof setTimeout> | undefined
    let delay = 1_000

    const connect = async () => {
      const controller = new AbortController()
      waiting = controller
      let denied = false
      const alive = () => {
        clearTimeout(heartbeat)
        heartbeat = setTimeout(() => controller.abort(), 35_000)
      }
      try {
        alive()
        const stream = await open(controller.signal)
        if (stopped) {
          await stream?.cancel()
          return
        }
        if (!stream) throw new ApiError(502, 'LIVE_UNAVAILABLE', '')
        alive()
        for await (const message of readEvents(stream)) {
          const { event } = message
          if (stopped) break
          controller.signal.throwIfAborted()
          alive()
          if (event === 'connected') {
            delay = 1_000
            setConnection({ source, connected: true })
            refresh()
          } else if (event === 'changed') refresh(message)
        }
      } catch (error) {
        denied = error instanceof ApiError && [400, 401, 403, 404].includes(error.status)
      } finally {
        clearTimeout(heartbeat)
        if (!stopped) {
          setConnection({ source, connected: false })
          if (!denied) {
            retry = setTimeout(() => void connect(), delay)
            delay = Math.min(delay * 2, 30_000)
          }
        }
      }
    }
    void connect()
    return () => {
      stopped = true
      waiting?.abort()
      clearTimeout(retry)
      clearTimeout(heartbeat)
    }
  }, [source, open, refresh])
  return { connected: source.enabled && connection.source === source && connection.connected }
}
