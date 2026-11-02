import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { AnswerActions } from '@/features/interview/AnswerBox'
import { api, ApiError, unwrap, type Schemas } from '@/lib/api/client'

export type InterviewAssignment = Schemas['InterviewAssignment']
export type StageInterviewAssignment = Schemas['StageInterviewAssignment']
export type InterviewMember = Schemas['InterviewMemberChoice']
export type AssignedInterview = Schemas['AssignedInterview']
export type InterviewerWorkspace = Schemas['InterviewerWorkspace']
export type InterviewerQuestion = Schemas['InterviewerQuestionAccess']

export const INTERVIEW_STATUS_LABELS = {
  SCHEDULED: '예정',
  IN_PROGRESS: '진행 중',
  ENDED: '끝남',
} as const satisfies Record<InterviewAssignment['status'], string>

/** 내 면접 목록은 별도 실시간 연결 없이 이 간격으로 상태를 다시 받아 온다 */
export const LIVE_POLL_MS = 5_000

export const sessionKeys = {
  members: ['interview', 'members'] as const,
  assignment: (stageId: string, applicationId: string) =>
    ['interview', 'session', stageId, applicationId] as const,
  stageAssignment: (stageId: string) => ['interview', 'assignment', stageId] as const,
  mine: ['interviewer', 'sessions'] as const,
  attendance: (stageId: string, applicationId: string) =>
    ['interviewer', 'attendance', stageId, applicationId] as const,
  progress: (stageId: string) => ['interview', 'progress', stageId] as const,
  workspace: (stageId: string, applicationId: string) =>
    ['interviewer', 'workspace', stageId, applicationId] as const,
}

/** 면접관으로 배정할 수 있는 같은 기업 계정 (HR, 면접관 계정) */
export function useInterviewMembers() {
  return useQuery({
    queryKey: sessionKeys.members,
    queryFn: () => unwrap(api.GET('/api/companies/current/interview-members')),
  })
}

/** 지원자 한 명의 면접관 배정과 진행 상태. 아직 배정하지 않았으면 null이다 */
export function useInterviewAssignment(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: sessionKeys.assignment(stageId, applicationId),
    queryFn: async (): Promise<InterviewAssignment | null> => {
      try {
        return await unwrap(
          api.GET('/api/stages/{stageId}/candidates/{applicationId}/interview/session', {
            params: { path: { stageId, applicationId } },
          }),
        )
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

/** 전형의 공통 면접관. 지원자가 없어도 미리 설정할 수 있다. */
export function useStageInterviewAssignment(stageId: string) {
  return useQuery({
    queryKey: sessionKeys.stageAssignment(stageId),
    queryFn: async (): Promise<StageInterviewAssignment | null> => {
      try {
        return await unwrap(
          api.GET('/api/stages/{stageId}/interview/assignment', {
            params: { path: { stageId } },
          }),
        )
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
  })
}

/** 한 번 저장한 배정을 이 전형의 모든 지원자가 함께 쓴다. */
export function useAssignStageInterview(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['InterviewAssignmentRequest']) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/interview/assignment', {
          params: { path: { stageId } },
          body,
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(sessionKeys.stageAssignment(stageId), saved)
      void queryClient.invalidateQueries({ queryKey: ['interview', 'session', stageId] })
      void queryClient.invalidateQueries({ queryKey: ['interviewer', 'workspace', stageId] })
      void queryClient.invalidateQueries({ queryKey: ['interviewer', 'attendance', stageId] })
      void queryClient.invalidateQueries({ queryKey: ['interview', 'opinions', stageId] })
      void queryClient.invalidateQueries({ queryKey: sessionKeys.progress(stageId) })
      void queryClient.invalidateQueries({ queryKey: sessionKeys.mine })
    },
  })
}

/** 로그인한 계정이 배정된 면접 (면접관 모드의 "내 면접") */
export function useMyInterviews() {
  return useQuery({
    queryKey: sessionKeys.mine,
    queryFn: async () => {
      const page = (index: number) =>
        unwrap(
          api.GET('/api/interviewer/sessions', {
            params: { query: { page: index, size: 50 } },
          }),
        )
      const first = await page(0)
      const rest = await Promise.all(
        Array.from({ length: Math.max(0, Math.ceil(first.total / 50) - 1) }, (_, index) =>
          page(index + 1),
        ),
      )
      const items = [...first.items, ...rest.flatMap((result) => result.items)]
      return { ...first, items, size: items.length }
    },
    refetchInterval: LIVE_POLL_MS,
  })
}

const workspacePath = (stageId: string, applicationId: string) => ({
  params: { path: { stageId, applicationId } },
})

/** 면접관 모드의 AI Chat 탭: 자기만 보는 탭. 처음 열면 서버가 하나 만든다 */
export function useInterviewerTab(stageId: string) {
  return useQuery({
    queryKey: ['interviewer', 'tab', stageId],
    queryFn: async () =>
      (await unwrap(api.GET('/api/stages/{stageId}/tabs', { params: { path: { stageId } } })))[0] ??
      null,
  })
}

/** 면접관 화면의 지원자 한 명: 내 담당, 질문별 권한, 개인 메모. 실시간 알림으로 다시 받아 온다 */
export function useWorkspace(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: sessionKeys.workspace(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET(
          '/api/interviewer/sessions/{stageId}/{applicationId}',
          workspacePath(stageId, applicationId),
        ),
      ),
  })
}

/**
 * 면접관 API의 동작. 시작, 종료, 메모는 바뀐 작업 공간으로 캐시를 바꾸고, 질문, 답변 변경은 면접 기록을 돌려주므로
 * 작업 공간(질문별 권한 포함)을 다시 받는다.
 */
export function useWorkspaceActions(stageId: string, applicationId: string) {
  const queryClient = useQueryClient()
  const onSuccess = (workspace: InterviewerWorkspace) => {
    queryClient.setQueryData(sessionKeys.workspace(stageId, applicationId), workspace)
    void queryClient.invalidateQueries({ queryKey: sessionKeys.mine })
  }
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: sessionKeys.workspace(stageId, applicationId) })
  const question = (questionId: string) => ({ params: { path: { stageId, questionId } } })
  return {
    end: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST(
            '/api/interviewer/sessions/{stageId}/{applicationId}/end',
            workspacePath(stageId, applicationId),
          ),
        ),
      onSuccess,
    }),
    memo: useMutation({
      mutationFn: (body: Schemas['PersonalInterviewMemo']) =>
        unwrap(
          api.PUT('/api/interviewer/sessions/{stageId}/{applicationId}/memo', {
            ...workspacePath(stageId, applicationId),
            body,
          }),
        ),
      onSuccess,
    }),
    add: useMutation({
      mutationFn: (body: Schemas['InterviewerManualQuestion']) =>
        unwrap(
          api.POST('/api/interviewer/sessions/{stageId}/{applicationId}/questions', {
            ...workspacePath(stageId, applicationId),
            body,
          }),
        ),
      onSuccess: refresh,
    }),
    remove: useMutation({
      mutationFn: (questionId: string) =>
        unwrap(
          api.DELETE(
            '/api/interviewer/sessions/{stageId}/questions/{questionId}',
            question(questionId),
          ),
        ),
      onSuccess: refresh,
    }),
    answer: useMutation({
      mutationFn: ({
        questionId,
        ...body
      }: { questionId: string } & Schemas['InterviewerAnswer']) =>
        unwrap(
          api.PUT('/api/interviewer/sessions/{stageId}/questions/{questionId}/answer', {
            ...question(questionId),
            body,
          }),
        ),
      onSuccess: refresh,
    }),
    suggest: useMutation({
      mutationFn: ({ questionId, avoid }: { questionId: string; avoid: string[] }) =>
        unwrap(
          api.POST(
            '/api/interviewer/sessions/{stageId}/questions/{questionId}/follow-ups/suggestions',
            {
              ...question(questionId),
              body: { avoid },
            },
          ),
        ),
    }),
    followUp: useMutation({
      mutationFn: ({
        questionId,
        ...body
      }: { questionId: string } & Schemas['InterviewerFollowUp']) =>
        unwrap(
          api.POST('/api/interviewer/sessions/{stageId}/questions/{questionId}/follow-ups', {
            ...question(questionId),
            body,
          }),
        ),
      onSuccess: refresh,
    }),
  }
}

/** 면접관 화면의 답변 칸 동작 (면접관 API로 저장, 꼬리질문) */
export function workspaceAnswerActions(
  actions: ReturnType<typeof useWorkspaceActions>,
): AnswerActions {
  return {
    save: async (input) => (await actions.answer.mutateAsync(input)).questions,
    suggest: (input) => actions.suggest.mutateAsync(input),
    // 직접 쓴 꼬리질문은 확인 포인트가 없다. 면접관 API는 빈 문자열을 확인 포인트 없음으로 받는다
    addFollowUp: (input) => actions.followUp.mutateAsync({ ...input, check: input.check ?? '' }),
    adding: actions.followUp.isPending,
  }
}
