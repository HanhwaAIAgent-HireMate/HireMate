import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  useInterviewReady,
  useInterviewAttendance,
  useInterviewRoomLive,
  useInterviewStageLive,
  useStageInterviewProgress,
  type InterviewAttendance,
} from './live'
import { sessionKeys, useInterviewAssignment, useWorkspace } from './sessions'
import { resetCsrf } from '@/lib/api/client'

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

function connection(request: Request) {
  let controller: ReadableStreamDefaultController<Uint8Array>
  let closed = false
  const body = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value
      request.signal.addEventListener('abort', () => {
        if (closed) return
        closed = true
        controller.error(new DOMException('Aborted', 'AbortError'))
      })
    },
    cancel() {
      closed = true
    },
  })
  return {
    request,
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    send(event: string, data = '{}') {
      if (!closed) controller.enqueue(new TextEncoder().encode(`event:${event}\ndata:${data}\n\n`))
    },
    close() {
      closed = true
      controller.close()
    },
  }
}

const attendance = (): InterviewAttendance => ({
  stageActive: true,
  attendees: [
    { role: 'HR', memberId: 'hr', name: '인사', ready: false, online: true, me: true },
    {
      role: 'PRACTICAL',
      memberId: 'practical',
      name: '실무',
      ready: true,
      online: true,
      me: false,
    },
  ],
})

const assignment = (status: 'SCHEDULED' | 'IN_PROGRESS' | 'ENDED' = 'SCHEDULED') => ({
  stageId: 'stage',
  applicationId: 'kim',
  hrMemberId: 'hr',
  practicalMemberId: 'practical',
  status,
  startedAt: null,
  endedAt: null,
  version: 0,
})

const workspace = (status: 'SCHEDULED' | 'IN_PROGRESS' | 'ENDED') => ({
  session: assignment(status),
  myRole: 'HR',
  personalMemo: '',
  questions: [],
  previous: [],
  schedule: null,
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  resetCsrf()
})

describe('면접 실시간 알림', () => {
  it('시작 전에도 다른 면접관의 시작 알림을 받아 질문 권한과 준비 현황을 다시 읽는다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    let status: 'SCHEDULED' | 'IN_PROGRESS' = 'SCHEDULED'
    let current = attendance()
    vi.stubGlobal('fetch', (request: Request) => {
      if (request.url.endsWith('/events')) {
        const stream = connection(request)
        streams.push(stream)
        return Promise.resolve(stream.response)
      }
      if (request.url.endsWith('/attendance')) return Promise.resolve(Response.json(current))
      return Promise.resolve(Response.json(workspace(status)))
    })
    const { client, wrapper } = setup()
    const hook = renderHook(
      () => ({
        live: useInterviewRoomLive('stage', 'kim'),
        room: useWorkspace('stage', 'kim'),
        attendance: useInterviewAttendance('stage', 'kim'),
      }),
      { wrapper },
    )
    await waitFor(() => expect(hook.result.current.room.data?.session.status).toBe('SCHEDULED'))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.live.connected).toBe(true))
    status = 'IN_PROGRESS'
    current = {
      ...current,
      attendees: current.attendees.map((person) => ({ ...person, ready: true })),
    }
    streams[0].send('changed', '{"applicationId":"kim"}')
    await waitFor(() => expect(hook.result.current.room.data?.session.status).toBe('IN_PROGRESS'))
    await waitFor(() => expect(hook.result.current.attendance.data?.attendees[0].ready).toBe(true))
    hook.unmount()
    expect(streams[0].request.signal.aborted).toBe(true)
    client.clear()
  })

  it('연결이 끊기면 다시 연결하고 놓친 종료 상태를 새로 읽는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const streams: ReturnType<typeof connection>[] = []
    let status: 'IN_PROGRESS' | 'ENDED' = 'IN_PROGRESS'
    vi.stubGlobal('fetch', (request: Request) => {
      if (request.url.endsWith('/events')) {
        const stream = connection(request)
        streams.push(stream)
        return Promise.resolve(stream.response)
      }
      return Promise.resolve(Response.json(workspace(status)))
    })
    const { client, wrapper } = setup()
    const hook = renderHook(
      () => ({
        live: useInterviewRoomLive('stage', 'kim'),
        room: useWorkspace('stage', 'kim'),
      }),
      { wrapper },
    )
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.live.connected).toBe(true))
    act(() => streams[0].close())
    await waitFor(() => expect(hook.result.current.live.connected).toBe(false))
    status = 'ENDED'
    await act(() => vi.advanceTimersByTimeAsync(1100))
    await waitFor(() => expect(streams).toHaveLength(2))
    streams[1].send('connected')
    await waitFor(() => expect(hook.result.current.room.data?.session.status).toBe('ENDED'))
    hook.unmount()
    client.clear()
  })

  it('지원자를 옮기면 기존 연결을 닫고 새 연결을 열어 이전 지원자와 구분한다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      const stream = connection(request)
      streams.push(stream)
      return Promise.resolve(stream.response)
    })
    const { client, wrapper } = setup()
    const hook = renderHook(({ id }) => useInterviewRoomLive('stage', id), {
      wrapper,
      initialProps: { id: 'kim' },
    })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.connected).toBe(true))
    hook.rerender({ id: 'lee' })
    expect(streams[0].request.signal.aborted).toBe(true)
    expect(hook.result.current.connected).toBe(false)
    await waitFor(() => expect(streams).toHaveLength(2))
    expect(streams[1].request.url).toContain('/stage/lee/events')
    hook.unmount()
    client.clear()
  })

  it('권한이 없어진 연결은 재시도하지 않는다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    let reads = 0
    vi.stubGlobal('fetch', () => {
      reads++
      return Promise.resolve(Response.json({ code: 'FORBIDDEN' }, { status: 403 }))
    })
    const { client, wrapper } = setup()
    const hook = renderHook(() => useInterviewRoomLive('stage', 'kim'), { wrapper })
    await waitFor(() => expect(reads).toBe(1))
    await act(() => vi.advanceTimersByTimeAsync(30_000))
    expect(reads).toBe(1)
    expect(hook.result.current.connected).toBe(false)
    hook.unmount()
    client.clear()
  })

  it('면접 전형에서만 HR 연결을 열고 시작 알림 뒤 배정 잠금과 진행 현황을 갱신한다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    let status: 'SCHEDULED' | 'IN_PROGRESS' = 'SCHEDULED'
    vi.stubGlobal('fetch', (request: Request) => {
      if (request.url.endsWith('/events')) {
        const stream = connection(request)
        streams.push(stream)
        return Promise.resolve(stream.response)
      }
      if (request.url.endsWith('/sessions'))
        return Promise.resolve(
          Response.json([{ ...assignment(status), attendees: attendance().attendees }]),
        )
      return Promise.resolve(Response.json(assignment(status)))
    })
    const { client, wrapper } = setup()
    const hook = renderHook(
      ({ enabled }) => ({
        live: useInterviewStageLive('stage', enabled),
        progress: useStageInterviewProgress('stage', enabled),
        assigned: useInterviewAssignment('stage', 'kim'),
      }),
      { wrapper, initialProps: { enabled: false } },
    )
    await waitFor(() => expect(hook.result.current.assigned.data?.status).toBe('SCHEDULED'))
    expect(streams).toHaveLength(0)
    expect(hook.result.current.progress.data).toBeUndefined()
    hook.rerender({ enabled: true })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.progress.data?.[0].status).toBe('SCHEDULED'))
    status = 'IN_PROGRESS'
    streams[0].send('changed', '{"applicationId":"kim"}')
    await waitFor(() => expect(hook.result.current.progress.data?.[0].status).toBe('IN_PROGRESS'))
    await waitFor(() => expect(hook.result.current.assigned.data?.status).toBe('IN_PROGRESS'))
    hook.unmount()
    client.clear()
  })

  it('지원자가 없는 전형도 공통 면접관 변경 알림으로 설정을 다시 읽는다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      const stream = connection(request)
      streams.push(stream)
      return Promise.resolve(stream.response)
    })
    const { client, wrapper } = setup()
    const hook = renderHook(() => useInterviewStageLive('stage'), { wrapper })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.connected).toBe(true))
    const key = sessionKeys.stageAssignment('stage')
    client.setQueryData(key, {
      stageId: 'stage',
      hrMemberId: 'hr',
      practicalMemberId: 'practical',
      version: 0,
      locked: false,
    })
    client.setQueryData(sessionKeys.stageAssignment('other'), {})
    streams[0].send('changed', '{}')
    await waitFor(() => expect(client.getQueryState(key)?.isInvalidated).toBe(true))
    expect(client.getQueryState(sessionKeys.stageAssignment('other'))?.isInvalidated).toBe(false)
    hook.unmount()
    client.clear()
  })

  it('HR 연결 성공 시에는 놓친 변경을 위해 모든 지원자의 캐시를 갱신한다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      const stream = connection(request)
      streams.push(stream)
      return Promise.resolve(stream.response)
    })
    const { client, wrapper } = setup()
    client.setQueryData(sessionKeys.assignment('stage', 'kim'), assignment())
    client.setQueryData(sessionKeys.assignment('stage', 'lee'), assignment())
    client.setQueryData(['stage', 'stage', 'interview', 'lee'], { questions: [] })
    const hook = renderHook(() => useInterviewStageLive('stage'), { wrapper })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.connected).toBe(true))
    expect(client.getQueryState(sessionKeys.assignment('stage', 'kim'))?.isInvalidated).toBe(true)
    expect(client.getQueryState(sessionKeys.assignment('stage', 'lee'))?.isInvalidated).toBe(true)
    expect(client.getQueryState(['stage', 'stage', 'interview', 'lee'])?.isInvalidated).toBe(true)
    hook.unmount()
    client.clear()
  })

  it('HR 변경 알림은 해당 지원자의 배정과 질문만 무효화한다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      const stream = connection(request)
      streams.push(stream)
      return Promise.resolve(stream.response)
    })
    const { client, wrapper } = setup()
    const kimQuestions = ['stage', 'stage', 'interview', 'kim']
    const leeQuestions = ['stage', 'stage', 'interview', 'lee']
    const hook = renderHook(() => useInterviewStageLive('stage'), { wrapper })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.connected).toBe(true))
    client.setQueryData(sessionKeys.assignment('stage', 'kim'), assignment())
    client.setQueryData(sessionKeys.assignment('stage', 'lee'), {
      ...assignment(),
      applicationId: 'lee',
    })
    client.setQueryData(kimQuestions, { questions: [] })
    client.setQueryData(leeQuestions, { questions: [] })
    client.setQueryData(sessionKeys.progress('stage'), [])
    streams[0].send('changed', '{"applicationId":"kim"}')
    await waitFor(() => expect(client.getQueryState(kimQuestions)?.isInvalidated).toBe(true))
    expect(client.getQueryState(sessionKeys.assignment('stage', 'kim'))?.isInvalidated).toBe(true)
    expect(client.getQueryState(sessionKeys.progress('stage'))?.isInvalidated).toBe(true)
    expect(client.getQueryState(sessionKeys.assignment('stage', 'lee'))?.isInvalidated).toBe(false)
    expect(client.getQueryState(leeQuestions)?.isInvalidated).toBe(false)
    hook.unmount()
    client.clear()
  })

  it.each(['broken json', '{}', '{"applicationId":42}', '{"applicationId":" "}', 'null'])(
    'HR 변경 알림의 지원자를 확인할 수 없으면 전체 후보 캐시를 다시 읽는다 (%s)',
    async (data) => {
      const streams: ReturnType<typeof connection>[] = []
      vi.stubGlobal('fetch', (request: Request) => {
        const stream = connection(request)
        streams.push(stream)
        return Promise.resolve(stream.response)
      })
      const { client, wrapper } = setup()
      const hook = renderHook(() => useInterviewStageLive('stage'), { wrapper })
      await waitFor(() => expect(streams).toHaveLength(1))
      streams[0].send('connected')
      await waitFor(() => expect(hook.result.current.connected).toBe(true))
      client.setQueryData(sessionKeys.assignment('stage', 'lee'), assignment())
      client.setQueryData(['stage', 'stage', 'interview', 'lee'], { questions: [] })
      streams[0].send('changed', data)
      await waitFor(() =>
        expect(client.getQueryState(sessionKeys.assignment('stage', 'lee'))?.isInvalidated).toBe(
          true,
        ),
      )
      expect(client.getQueryState(['stage', 'stage', 'interview', 'lee'])?.isInvalidated).toBe(true)
      hook.unmount()
      client.clear()
    },
  )

  it('구독을 껐다 켜면 이전 연결을 접속 중으로 표시하지 않는다', async () => {
    const streams: ReturnType<typeof connection>[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      const stream = connection(request)
      streams.push(stream)
      return Promise.resolve(stream.response)
    })
    const { client, wrapper } = setup()
    const hook = renderHook(({ enabled }) => useInterviewStageLive('stage', enabled), {
      wrapper,
      initialProps: { enabled: true },
    })
    await waitFor(() => expect(streams).toHaveLength(1))
    streams[0].send('connected')
    await waitFor(() => expect(hook.result.current.connected).toBe(true))
    hook.rerender({ enabled: false })
    expect(streams[0].request.signal.aborted).toBe(true)
    hook.rerender({ enabled: true })
    expect(hook.result.current.connected).toBe(false)
    hook.unmount()
    client.clear()
  })

  it('서버 응답이 오지 않는 연결도 제한 시간 뒤 끊고 재시도한다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const requests: Request[] = []
    vi.stubGlobal('fetch', (request: Request) => {
      requests.push(request)
      return new Promise<Response>((_resolve, reject) => {
        request.signal.addEventListener('abort', () =>
          reject(new DOMException('Aborted', 'AbortError')),
        )
      })
    })
    const { client, wrapper } = setup()
    const hook = renderHook(() => useInterviewRoomLive('stage', 'kim'), { wrapper })
    await waitFor(() => expect(requests).toHaveLength(1))
    await act(() => vi.advanceTimersByTimeAsync(36_100))
    expect(requests[0].signal.aborted).toBe(true)
    expect(requests).toHaveLength(2)
    hook.unmount()
    client.clear()
  })

  it('준비 완료 · 취소 결과로 준비 현황을 바로 바꾸고, 시작했을 수 있는 면접 상태를 다시 읽는다', async () => {
    let current = attendance()
    let workspaceReads = 0
    const calls: string[] = []
    resetCsrf()
    vi.stubGlobal('fetch', (request: Request | string) => {
      const url = typeof request === 'string' ? request : request.url
      if (url.endsWith('/csrf'))
        return Promise.resolve(Response.json({ token: 'token', headerName: 'X-CSRF-TOKEN' }))
      if (typeof request !== 'string' && url.endsWith('/ready')) {
        calls.push(request.method)
        const ready = request.method === 'POST'
        current = {
          ...current,
          attendees: current.attendees.map((person) => (person.me ? { ...person, ready } : person)),
        }
        return Promise.resolve(Response.json(current))
      }
      if (url.endsWith('/attendance')) return Promise.resolve(Response.json(current))
      workspaceReads += 1
      return Promise.resolve(Response.json(workspace('SCHEDULED')))
    })
    const { client, wrapper } = setup()
    const hook = renderHook(
      () => ({
        attendance: useInterviewAttendance('stage', 'kim'),
        room: useWorkspace('stage', 'kim'),
        readiness: useInterviewReady('stage', 'kim'),
      }),
      { wrapper },
    )
    await waitFor(() => expect(hook.result.current.attendance.data?.attendees[0].ready).toBe(false))
    await waitFor(() => expect(workspaceReads).toBe(1))
    await act(() => hook.result.current.readiness.ready.mutateAsync())
    expect(client.getQueryData(sessionKeys.attendance('stage', 'kim'))).toEqual(current)
    await waitFor(() => expect(hook.result.current.attendance.data?.attendees[0].ready).toBe(true))
    // 두 번째 준비 완료면 서버가 면접을 시작했을 수 있어 면접 상태를 다시 읽는다
    await waitFor(() => expect(workspaceReads).toBe(2))
    await act(() => hook.result.current.readiness.cancel.mutateAsync())
    await waitFor(() => expect(hook.result.current.attendance.data?.attendees[0].ready).toBe(false))
    expect(calls).toEqual(['POST', 'DELETE'])
    hook.unmount()
    client.clear()
  })
})
