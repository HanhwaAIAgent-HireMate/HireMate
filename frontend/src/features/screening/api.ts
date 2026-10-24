import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type StageOverview = Schemas['StageOverview']
export type CandidateRow = Schemas['CandidateRow']
export type CandidateDetail = Schemas['CandidateDetail']
export type CandidateAnalysis = Schemas['CandidateAnalysis']
export type CriterionLine = Schemas['CriterionLine']
export type Decision = CandidateRow['decision']

const PAGE_SIZE = 30
/** 분석 중인 지원자가 있으면 이 간격으로 다시 불러온다. 분석은 AI 워커가 대기열에서 하나씩 처리해 몇 분 걸린다 */
const ANALYSIS_POLL_MS = 5000

/** 분석 중(PENDING)인 지원자가 있는가 */
export function hasPendingAnalysis(rows: Pick<CandidateRow, 'analysisStatus'>[]) {
  return rows.some((row) => row.analysisStatus === 'PENDING')
}

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
    refetchInterval: (query) =>
      hasPendingAnalysis(query.state.data?.pages.flatMap((page) => page.items) ?? [])
        ? ANALYSIS_POLL_MS
        : false,
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
    refetchInterval: (query) =>
      query.state.data?.row.analysisStatus === 'PENDING' ? ANALYSIS_POLL_MS : false,
  })
}

/**
 * 카드의 AI 분석. 분석이 끝난 지원자만 불러온다. 분석 중에 부르면 ai 서버가 워커와 따로 분석을 시작하기 때문이다.
 * 분석 상태가 바뀌면(분석 중 → 끝남) 새로 불러온다
 */
export function useCandidateAnalysis(
  stageId: string,
  applicationId: string,
  status: CandidateRow['analysisStatus'],
) {
  return useQuery({
    queryKey: [...stageKeys.analysis(stageId, applicationId), status],
    enabled: status === 'DONE',
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

/** 분석에 실패한 지원자를 다시 분석한다. 결과는 분석이 끝나면 리스트와 카드에 반영된다 */
export function useRetryAnalysis(stageId: string, recruitmentId: string, applicationId: string) {
  return useStageMutation(stageId, () =>
    unwrap(
      api.POST('/api/recruitments/{recruitmentId}/applications/{applicationId}/analysis', {
        params: { path: { recruitmentId, applicationId } },
      }),
    ),
  )
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

/** 서류 평가 점수 같은 소수 첫째 자리 점수 (예: 73.3) */
export function formatScore(value: number) {
  return value.toFixed(1)
}

/** "자격요건 33.3/50 · 우대사항 40.0/50". 확인 필요 항목이 있는 영역은 "확인 필요", 분석 전이면 null */
export function scoreBreakdown(
  row: Pick<
    CandidateRow,
    'qualificationScore' | 'qualificationMax' | 'preferenceScore' | 'preferenceMax'
  >,
) {
  const parts = [
    ['자격요건', row.qualificationScore, row.qualificationMax] as const,
    ['우대사항', row.preferenceScore, row.preferenceMax] as const,
  ]
    .filter(([, , max]) => max > 0)
    .map(([label, score, max]) =>
      score === null ? `${label} 확인 필요` : `${label} ${formatScore(score)}/${max}`,
    )
  return parts.length > 0 ? parts.join(' · ') : null
}

/** "경력 5년 · OO카드", 신입은 "신입". 분석은 끝났는데 서류에서 경력을 읽지 못하면 "경력 확인 필요" */
export function careerLabel(
  row: Pick<CandidateRow, 'careerYears' | 'lastCompany' | 'analysisStatus'>,
) {
  if (row.careerYears === null) {
    if (row.analysisStatus === 'DONE') return '경력 확인 필요'
    return row.analysisStatus === 'FAILED' ? '분석 실패' : '분석 중'
  }
  if (row.careerYears === 0) return '신입'
  return [`경력 ${row.careerYears}년`, row.lastCompany].filter(Boolean).join(' · ')
}

/** 전형 지원자 전체 (결과 등록 창처럼 한 번에 다 보여 줄 때) */
export function useAllCandidates(stageId: string, enabled = true) {
  return useQuery({
    queryKey: [...stageKeys.all(stageId), 'all-candidates'],
    enabled,
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates', {
          params: { path: { stageId }, query: { page: 0, size: 200 } },
        }),
      ),
  })
}
