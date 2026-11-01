import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type OpinionView = Schemas['OpinionView']
export type Recommendation = Schemas['OpinionRequest']['recommendation']
export type CandidateOpinions = Schemas['CandidateOpinions']

export const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  RECOMMEND: '추천',
  HOLD: '보류',
  NOT_RECOMMEND: '비추천',
}

/** 추천도 색: 추천은 합격 색, 비추천은 불합격 색, 보류는 노랑 */
export const RECOMMENDATION_STYLES: Record<Recommendation, string> = {
  RECOMMEND: 'border-pass-foreground/40 bg-pass text-pass-foreground',
  HOLD: 'border-amber-300 bg-amber-50 text-amber-800',
  NOT_RECOMMEND: 'border-fail-foreground/40 bg-fail text-fail-foreground',
}

export const opinionKeys = {
  mine: (stageId: string, applicationId: string) =>
    ['interviewer', 'opinions', stageId, applicationId] as const,
  candidate: (stageId: string, applicationId: string) =>
    ['interview', 'opinions', stageId, applicationId] as const,
  stage: (stageId: string) => ['interview', 'opinions', stageId] as const,
}

/** 면접관이 보는 의견. 내 의견을 저장하기 전에는 다른 면접관 의견의 내용이 비어 있다 */
export function useMyOpinions(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: opinionKeys.mine(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/interviewer/sessions/{stageId}/{applicationId}/opinions', {
          params: { path: { stageId, applicationId } },
        }),
      ),
  })
}

export function useSaveOpinion(stageId: string, applicationId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: Schemas['OpinionRequest']) =>
      unwrap(
        api.PUT('/api/interviewer/sessions/{stageId}/{applicationId}/opinions/me', {
          params: { path: { stageId, applicationId } },
          body,
        }),
      ),
    onSuccess: (saved) => queryClient.setQueryData(opinionKeys.mine(stageId, applicationId), saved),
  })
}

/** HR이 보는 지원자 한 명의 의견 (모두 보인다) */
export function useCandidateOpinions(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: opinionKeys.candidate(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates/{applicationId}/interview/opinions', {
          params: { path: { stageId, applicationId } },
        }),
      ),
  })
}

/** HR 지원자 목록의 의견 배지 · 결정 경고. 면접 전형에서만 부른다 */
export function useStageOpinions(stageId: string, enabled: boolean) {
  return useQuery({
    queryKey: opinionKeys.stage(stageId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/interview/opinions', { params: { path: { stageId } } }),
      ),
    enabled,
  })
}

/** 의견이 빠진 담당 이름 (예: ['실무']). 배정되지 않은 지원자는 비어 있다 */
export function missingOpinions(row: CandidateOpinions | undefined) {
  return (row?.opinions ?? [])
    .filter((opinion) => !opinion.unassigned && !opinion.submitted)
    .map((opinion) => (opinion.role === 'HR' ? '인사' : '실무'))
}
