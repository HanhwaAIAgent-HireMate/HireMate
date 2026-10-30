import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'
import { stageKeys } from '@/features/screening/api'
import { formatDateTime } from '@/lib/format'

export type Interview = Schemas['InterviewView']
export type InterviewQuestion = Schemas['Question']
export type FollowUps = Schemas['InterviewFollowUps']
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
      const status = await unwrap(
        api.GET(
          '/api/stages/{stageId}/candidates/{applicationId}/interview/preparing',
          path(stageId, applicationId),
        ),
      )
      if (!status.preparing)
        await queryClient.invalidateQueries({ queryKey: key(stageId, applicationId), exact: true })
      return status
    },
    refetchInterval: (query) =>
      query.state.data?.preparing ||
      !queryClient.getQueryData<Interview>(key(stageId, applicationId))?.questions.length
        ? PREPARING_POLL_MS
        : false,
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
    assignRole: useMutation({
      mutationFn: ({
        questionId,
        interviewerRole,
      }: {
        questionId: string
        interviewerRole: 'HR' | 'PRACTICAL' | null
      }) =>
        unwrap(
          api.PUT('/api/stages/{stageId}/interview/questions/{questionId}/role', {
            params: { path: { stageId, questionId } },
            body: { interviewerRole },
          }),
        ),
      onSuccess,
    }),
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
            body: { text, interviewerRole: null },
          }),
        ),
      onSuccess,
    }),
    /**
     * 💾 답변 저장. analyze가 false면 자동 저장(DB에만 저장, 분석 없음), true면 답변 칸을 떠날 때라 분석까지 요청한다.
     * 같은 답으로 칸을 여러 번 드나들어도 서버가 한 번만 분석한다.
     */
    answer: useMutation({
      mutationFn: ({
        questionId,
        answer,
        analyze = true,
      }: {
        questionId: string
        answer: string
        analyze?: boolean
      }) =>
        unwrap(
          api.PUT('/api/stages/{stageId}/interview/questions/{questionId}/answer', {
            params: { path: { stageId, questionId } },
            body: { answer, analyze },
          }),
        ),
      onSuccess,
    }),
    /**
     * 🎤 [꼬리질문 받기] · [다시 제안]. 누를 때만 모델을 부른다. 제안은 저장하지 않는다.
     * avoid는 [다시 제안]일 때 앞서 보여 준 제안이다.
     */
    suggestFollowUps: useMutation({
      mutationFn: ({ questionId, avoid }: { questionId: string; avoid: string[] }) =>
        unwrap(
          api.POST(
            '/api/stages/{stageId}/interview/questions/{questionId}/follow-ups/suggestions',
            {
              params: { path: { stageId, questionId } },
              body: { avoid },
            },
          ),
        ),
    }),
    /** 🎤 고른(또는 직접 쓴) 꼬리질문을 원래 질문 아래에 넣는다. 담당은 원래 질문을 잇는다. */
    addFollowUp: useMutation({
      mutationFn: ({
        questionId,
        text,
        source,
        check,
      }: {
        questionId: string
        text: string
        source: 'AI' | 'MANUAL'
        check: string | null
      }) =>
        unwrap(
          api.POST('/api/stages/{stageId}/interview/questions/{questionId}/follow-ups', {
            params: { path: { stageId, questionId } },
            body: { text, source, check },
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
