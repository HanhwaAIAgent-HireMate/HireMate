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
      mutationFn: ({
        text,
        interviewerRole,
      }: {
        text: string
        interviewerRole: 'HR' | 'PRACTICAL'
      }) =>
        unwrap(
          api.POST('/api/stages/{stageId}/candidates/{applicationId}/interview/questions', {
            ...path(stageId, applicationId),
            body: { text, interviewerRole },
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
        expectedVersion,
      }: {
        questionId: string
        answer: string
        analyze?: boolean
        expectedVersion: number
      }) =>
        unwrap(
          api.PUT('/api/stages/{stageId}/interview/questions/{questionId}/answer', {
            params: { path: { stageId, questionId } },
            body: { answer, analyze, expectedVersion },
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
      onSuccess: (data) => {
        onSuccess(data)
        // 함께 면접 볼 사람이 바뀌니 시간별 목록과 면접 진행 현황도 다시 읽는다
        void queryClient.invalidateQueries({ queryKey: scheduleKey(stageId) })
        void queryClient.invalidateQueries({ queryKey: ['interview', 'progress', stageId] })
      },
    }),
  }
}

const scheduleKey = (stageId: string) => [...stageKeys.all(stageId), 'interview', 'schedules']

/** 전형의 면접 일시 (일시를 정한 지원자만). 같은 일시의 지원자는 한 면접으로 함께 본다 */
export function useStageSchedules(stageId: string, enabled = true) {
  return useQuery({
    queryKey: scheduleKey(stageId),
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/interview/schedules', { params: { path: { stageId } } }),
      ),
  })
}

/** 면접 일시만 표시한다. 담당자 이름은 실제 배정·준비 현황에서 읽는다. */
export function scheduleLabel(schedule: Interview['schedule']) {
  return schedule?.scheduledAt ? formatDateTime(schedule.scheduledAt) : null
}
