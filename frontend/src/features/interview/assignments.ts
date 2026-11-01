import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type StageInterviewers = Schemas['StageInterviewers']
export type InterviewerSlot = Schemas['InterviewerSlot']
export type AssignedStage = Schemas['AssignedStage']

export const assignmentKeys = {
  stage: (stageId: string) => ['interview', 'interviewers', stageId] as const,
  mine: ['interviewer', 'stages'] as const,
}

/** 면접 전형에 지정한 면접관 (담당별) */
export function useStageInterviewers(stageId: string, enabled = true) {
  return useQuery({
    queryKey: assignmentKeys.stage(stageId),
    queryFn: () =>
      unwrap(api.GET('/api/stages/{stageId}/interviewers', { params: { path: { stageId } } })),
    enabled,
  })
}

/** 담당별 면접관을 통째로 바꾼다. 빠진 담당은 지정이 풀린다 */
export function useAssignInterviewers(stageId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (slots: Schemas['InterviewerSlotRequest'][]) =>
      unwrap(
        api.PUT('/api/stages/{stageId}/interviewers', {
          params: { path: { stageId } },
          body: { slots },
        }),
      ),
    onSuccess: (saved) => {
      queryClient.setQueryData(assignmentKeys.stage(stageId), saved)
      void queryClient.invalidateQueries({ queryKey: assignmentKeys.mine })
    },
  })
}

/** 로그인한 계정이 지정된 면접 전형 ("내 면접") */
export function useMyInterviews() {
  return useQuery({
    queryKey: assignmentKeys.mine,
    queryFn: () => unwrap(api.GET('/api/interviewer/stages')),
  })
}
