import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'
import { formatDateTime } from '@/lib/format'

export type Interview = Schemas['InterviewView']
export type StageHistory = Schemas['StageCandidateView']

const key = (stageId: string, applicationId: string) => [
  ...stageKeys.all(stageId),
  'interview',
  applicationId,
]
const path = (stageId: string, applicationId: string) => ({
  params: { path: { stageId, applicationId } },
})

export function useInterview(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: key(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/stages/{stageId}/candidates/{applicationId}/interview',
          path(stageId, applicationId),
        ),
      ),
  })
}

/** 질문 생성 중일 때 다시 묻는 간격. 실제 모델은 한 명에 1~3분 걸린다 */
const PREPARING_POLL_MS = 3_000

/**
 * 면접 전형이 시작되면 AI 워커가 맞춤 질문을 미리 만든다 (FR-27). 만드는 중이면 몇 초마다 다시 묻고,
 * 끝나면(만드는 중 → 끝남) 카드 질문을 새로 불러와 새로고침 없이 질문이 나타나게 한다.
 */
export function useInterviewPreparing(stageId: string, applicationId: string) {
  const queryClient = useQueryClient()
  const preparingKey = [...key(stageId, applicationId), 'preparing']
  return useQuery({
    queryKey: preparingKey,
    queryFn: async () => {
      const before = queryClient.getQueryData<{ preparing: boolean }>(preparingKey)
      const status = await unwrap(
        api.GET(
          '/api/stages/{stageId}/candidates/{applicationId}/interview/preparing',
          path(stageId, applicationId),
        ),
      )
      if (finishedPreparing(before, status))
        await queryClient.invalidateQueries({ queryKey: key(stageId, applicationId), exact: true })
      return status
    },
    refetchInterval: (query) => (query.state.data?.preparing ? PREPARING_POLL_MS : false),
  })
}

/** 직전에는 만드는 중이었는데 지금은 끝났는가. 이때만 카드 질문을 다시 불러온다 */
export function finishedPreparing(
  before: { preparing: boolean } | undefined,
  now: { preparing: boolean },
) {
  return before?.preparing === true && !now.preparing
}

export function useStageHistory(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: [...stageKeys.all(stageId), 'history', applicationId],
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/stages/{stageId}/candidates/{applicationId}/history',
          path(stageId, applicationId),
        ),
      ),
  })
}

/** 질문 · 답변 · 일정 변경. 서버가 돌려준 면접 기록으로 캐시를 바꾼다. */
export function useInterviewActions(stageId: string, applicationId: string) {
  const queryClient = useQueryClient()
  const onSuccess = (interview: Interview) =>
    queryClient.setQueryData(key(stageId, applicationId), interview)
  return {
    regenerate: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST(
            '/api/stages/{stageId}/candidates/{applicationId}/interview/questions/regenerate',
            path(stageId, applicationId),
          ),
        ),
      onSuccess: async () => {
        queryClient.setQueryData([...key(stageId, applicationId), 'preparing'], { preparing: true })
        await queryClient.invalidateQueries({ queryKey: key(stageId, applicationId) })
      },
    }),
    add: useMutation({
      mutationFn: (text: string) =>
        unwrap(
          api.POST('/api/stages/{stageId}/candidates/{applicationId}/interview/questions', {
            ...path(stageId, applicationId),
            body: { text },
          }),
        ),
      onSuccess,
    }),
    answer: useMutation({
      mutationFn: ({ questionId, answer }: { questionId: string; answer: string }) =>
        unwrap(
          api.PUT('/api/stages/{stageId}/interview/questions/{questionId}/answer', {
            params: { path: { stageId, questionId } },
            body: { answer },
          }),
        ),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: (questionId: string) =>
        unwrap(
          api.DELETE('/api/stages/{stageId}/interview/questions/{questionId}', {
            params: { path: { stageId, questionId } },
          }),
        ),
      onSuccess,
    }),
    schedule: useMutation({
      mutationFn: (body: { scheduledAt: string | null; interviewers: string }) =>
        unwrap(
          api.PUT('/api/stages/{stageId}/candidates/{applicationId}/interview/schedule', {
            ...path(stageId, applicationId),
            body,
          }),
        ),
      onSuccess,
    }),
  }
}

/** 면접 일정 한 줄. 예: 10.31 (금) 14:00 · 면접관 2명 */
export function scheduleLabel(schedule: Interview['schedule']) {
  if (!schedule) return null
  return [schedule.scheduledAt && formatDateTime(schedule.scheduledAt), schedule.interviewers]
    .filter(Boolean)
    .join(' · ')
}
