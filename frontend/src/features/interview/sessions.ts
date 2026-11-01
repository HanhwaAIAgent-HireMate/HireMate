import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import type { AnswerActions } from '@/features/interview/AnswerBox'
import { api, ApiError, unwrap, type Schemas } from '@/lib/api/client'

export type InterviewAssignment = Schemas['InterviewAssignment']
export type InterviewMember = Schemas['InterviewMemberChoice']
export type AssignedInterview = Schemas['AssignedInterview']
export type InterviewerWorkspace = Schemas['InterviewerWorkspace']
export type InterviewerQuestion = Schemas['InterviewerQuestionAccess']

/** 면접 중에는 다른 면접관의 답과 새 질문을 이 간격으로 다시 받아 온다 */
export const LIVE_POLL_MS = 5_000

export const sessionKeys = {
  members: ['interview', 'members'] as const,
  assignment: (stageId: string, applicationId: string) =>
    ['interview', 'session', stageId, applicationId] as const,
  mine: ['interviewer', 'sessions'] as const,
  workspace: (stageId: string, applicationId: string) =>
    ['interviewer', 'workspace', stageId, applicationId] as const,
}

/** 면접관으로 배정할 수 있는 같은 기업 계정 (HR · 면접관 계정) */
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

/** 인사 · 실무 면접관을 배정한다. 바꿀 때는 조회한 version을 보내고, 시작 뒤에는 서버가 거절한다 */
export function useAssignInterview(stageId: string, applicationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['InterviewAssignmentRequest']) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/candidates/{applicationId}/interview/session', {
          params: { path: { stageId, applicationId } },
          body,
        }),
      ),
    onSuccess: (saved) =>
      queryClient.setQueryData(sessionKeys.assignment(stageId, applicationId), saved),
  })
}

/** 로그인한 계정이 배정된 면접 (면접관 모드의 "내 면접") */
export function useMyInterviews() {
  return useQuery({
    queryKey: sessionKeys.mine,
    queryFn: () =>
      unwrap(api.GET('/api/interviewer/sessions', { params: { query: { page: 0, size: 50 } } })),
  })
}

const workspacePath = (stageId: string, applicationId: string) => ({
  params: { path: { stageId, applicationId } },
})

/** 면접관 화면의 지원자 한 명: 내 담당, 질문별 권한, 개인 메모. 진행 중이면 몇 초마다 다시 받아 온다 */
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
    refetchInterval: (query) =>
      query.state.data?.session.status === 'IN_PROGRESS' ? LIVE_POLL_MS : false,
  })
}

/**
 * 면접관 API의 동작. 시작 · 종료 · 메모는 바뀐 작업 공간으로 캐시를 바꾸고, 질문 · 답변 변경은 면접 기록을 돌려주므로
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
    start: useMutation({
      mutationFn: () =>
        unwrap(
          api.POST(
            '/api/interviewer/sessions/{stageId}/{applicationId}/start',
            workspacePath(stageId, applicationId),
          ),
        ),
      onSuccess,
    }),
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

/** 면접관 화면의 답변 칸 동작 (면접관 API로 저장 · 꼬리질문) */
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
