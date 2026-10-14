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
    generate: useMutation({
      mutationFn: (focus: string | null) =>
        unwrap(
          api.POST('/api/stages/{stageId}/candidates/{applicationId}/interview/generate', {
            ...path(stageId, applicationId),
            body: { focus },
          }),
        ),
      onSuccess,
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
