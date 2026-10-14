import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type StageOverview = Schemas['StageOverview']
export type CandidateRow = Schemas['CandidateRow']
export type CandidateDetail = Schemas['CandidateDetail']
export type CandidateAnalysis = Schemas['CandidateAnalysis']
export type Decision = CandidateRow['decision']

const PAGE_SIZE = 30

export const stageKeys = {
  all: (stageId: string) => ['stage', stageId] as const,
  overview: (stageId: string) => ['stage', stageId, 'overview'] as const,
  candidates: (stageId: string, query: string) => ['stage', stageId, 'candidates', query] as const,
  selection: (stageId: string) => ['stage', stageId, 'selection'] as const,
  detail: (stageId: string, applicationId: string) =>
    ['stage', stageId, 'detail', applicationId] as const,
  analysis: (stageId: string, applicationId: string) =>
    ['stage', stageId, 'analysis', applicationId] as const,
}

const path = (stageId: string) => ({ params: { path: { stageId } } })

export function useStageOverview(stageId: string) {
  return useQuery({
    queryKey: stageKeys.overview(stageId),
    queryFn: () => unwrap(api.GET('/api/stages/{stageId}', path(stageId))),
  })
}

/** 전체 지원자. 스크롤하면 이어서 불러온다. */
export function useCandidates(stageId: string, query: string) {
  return useInfiniteQuery({
    queryKey: stageKeys.candidates(stageId, query),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates', {
          params: {
            path: { stageId },
            query: { query: query || undefined, page: pageParam, size: PAGE_SIZE },
          },
        }),
      ),
    getNextPageParam: (last, pages) =>
      pages.reduce((sum, page) => sum + page.items.length, 0) < last.total
        ? pages.length
        : undefined,
  })
}

export function useSelection(stageId: string) {
  return useQuery({
    queryKey: stageKeys.selection(stageId),
    queryFn: () => unwrap(api.GET('/api/stages/{stageId}/selection', path(stageId))),
  })
}

export function useCandidateDetail(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: stageKeys.detail(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates/{applicationId}', {
          params: { path: { stageId, applicationId } },
        }),
      ),
  })
}

export function useCandidateAnalysis(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: stageKeys.analysis(stageId, applicationId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates/{applicationId}/analysis', {
          params: { path: { stageId, applicationId } },
        }),
      ),
    staleTime: 5 * 60 * 1000,
  })
}

/** 전형 화면의 변경 요청. 끝나면 리스트 · 선택 지원자 · 현황을 다시 불러온다. */
export function useStageMutation<T, R = unknown>(
  stageId: string,
  request: (variables: T) => Promise<R>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSettled: () => queryClient.invalidateQueries({ queryKey: stageKeys.all(stageId) }),
  })
}

export function useSelectionActions(stageId: string) {
  const body = (applicationIds: string[]) => ({ ...path(stageId), body: { applicationIds } })
  return {
    add: useStageMutation(stageId, (ids: string[]) =>
      unwrap(api.POST('/api/stages/{stageId}/selection/add', body(ids))),
    ),
    remove: useStageMutation(stageId, (ids: string[]) =>
      unwrap(api.POST('/api/stages/{stageId}/selection/remove', body(ids))),
    ),
    clear: useStageMutation(stageId, () =>
      unwrap(api.POST('/api/stages/{stageId}/selection/clear', path(stageId))),
    ),
    restore: useStageMutation(stageId, () =>
      unwrap(api.POST('/api/stages/{stageId}/selection/restore', path(stageId))),
    ),
    promote: useStageMutation(stageId, (applicationId: string) =>
      unwrap(
        api.POST('/api/stages/{stageId}/candidates/{applicationId}/promote', {
          params: { path: { stageId, applicationId } },
        }),
      ),
    ),
  }
}

export function useDecisionActions(stageId: string) {
  return {
    decide: useStageMutation(
      stageId,
      ({ ids, decision }: { ids: string[]; decision: 'PASS' | 'FAIL' }) =>
        unwrap(
          api.POST('/api/stages/{stageId}/decisions', {
            ...path(stageId),
            body: { applicationIds: ids, decision },
          }),
        ),
    ),
    revert: useStageMutation(stageId, (ids: string[]) =>
      unwrap(
        api.POST('/api/stages/{stageId}/decisions/revert', {
          ...path(stageId),
          body: { applicationIds: ids },
        }),
      ),
    ),
    confirm: useStageMutation(stageId, () =>
      unwrap(api.POST('/api/stages/{stageId}/confirm', path(stageId))),
    ),
  }
}

export function useSaveMemo(stageId: string, applicationId: string) {
  return useStageMutation(stageId, (memo: string) =>
    unwrap(
      api.PUT('/api/stages/{stageId}/candidates/{applicationId}/memo', {
        params: { path: { stageId, applicationId } },
        body: { memo },
      }),
    ),
  )
}

/** "경력 5년 · OO카드", 신입은 "신입" */
export function careerLabel(
  row: Pick<CandidateRow, 'careerYears' | 'lastCompany' | 'analysisStatus'>,
) {
  if (row.careerYears === null) return row.analysisStatus === 'FAILED' ? '분석 실패' : '분석 중'
  if (row.careerYears === 0) return '신입'
  return [`경력 ${row.careerYears}년`, row.lastCompany].filter(Boolean).join(' · ')
}
