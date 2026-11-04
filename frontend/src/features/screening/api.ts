import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

export type StageOverview = Schemas['StageOverview']
export type CandidateRow = Schemas['CandidateRow']
export type CandidateDetail = Schemas['CandidateDetail']
export type CandidateAnalysis = Schemas['CandidateAnalysis']
export type CriterionLine = Schemas['CriterionLine']
export type SummarySection = Schemas['SummarySection']
export type Decision = CandidateRow['decision']
/**
 * 전체 지원자 거르기. 결정 상태는 하나라도 맞으면 남고, 평가 항목(ID)과 인재상(표 보기 열 ID)은 고른 것이 모두
 * O 또는 중 이상이어야 남는다. 비어 있는 칸은 거르지 않는다
 */
export type CandidateFilter = { decisions: Decision[]; criteria: string[]; talents: string[] }

export const NO_FILTER: CandidateFilter = { decisions: [], criteria: [], talents: [] }

/** 거르기 조건이 하나라도 있는가 */
export function isFiltered(filter: CandidateFilter) {
  return filter.decisions.length + filter.criteria.length + filter.talents.length > 0
}

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
  tabs: (stageId: string) => ['stage', stageId, 'tabs'] as const,
  candidates: (stageId: string, tabId: string | null, query: string, filter: CandidateFilter) =>
    ['stage', stageId, 'candidates', tabId, query, filter] as const,
  selection: (stageId: string, tabId: string) => ['stage', stageId, 'selection', tabId] as const,
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

/**
 * 전체 지원자. 스크롤하면 이어서 불러온다. 서류 전형은 자격요건 + 우대사항 충족 개수에 상인 인재상 개수를 더한 순,
 * 평가 전형은 점수 높은 순이다. filter는 서버가 거른다. 선택 표시와 AI 테두리는 tabId 탭 기준이다.
 */
export function useCandidates(
  stageId: string,
  tabId: string | null,
  query: string,
  filter: CandidateFilter,
) {
  return useInfiniteQuery({
    queryKey: stageKeys.candidates(stageId, tabId, query, filter),
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates', {
          params: {
            path: { stageId },
            query: {
              tabId: tabId ?? undefined,
              query: query || undefined,
              decision: filter.decisions.length > 0 ? filter.decisions : undefined,
              criterion: filter.criteria.length > 0 ? filter.criteria : undefined,
              talent: filter.talents.length > 0 ? filter.talents : undefined,
              page: pageParam,
              size: PAGE_SIZE,
            },
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

/** 탭의 선택 지원자 */
export function useSelection(stageId: string, tabId: string) {
  return useQuery({
    queryKey: stageKeys.selection(stageId, tabId),
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/tabs/{tabId}/selection', {
          params: { path: { stageId, tabId } },
        }),
      ),
  })
}

export function useCandidateDetail(stageId: string, applicationId: string) {
  return useQuery({
    queryKey: stageKeys.detail(stageId, applicationId),
    enabled: applicationId !== '',
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
    // 다시 불러오기를 기다리지 않는다. 카드 AI 분석은 결정 · 넣기 · 빼기로 바뀌지 않아 다시 부르지 않는다
    onSettled: () => {
      void queryClient.invalidateQueries({
        queryKey: stageKeys.all(stageId),
        predicate: (query) => query.queryKey[2] !== 'analysis',
      })
    },
  })
}

/** 탭의 선택 지원자 편집. 기준선 ↑는 탭과 상관없다. */
export function useSelectionActions(stageId: string, tabId: string) {
  const tabPath = { params: { path: { stageId, tabId } } }
  const body = (applicationIds: string[]) => ({ ...tabPath, body: { applicationIds } })
  return {
    add: useStageMutation(stageId, (ids: string[]) =>
      unwrap(api.POST('/api/stages/{stageId}/tabs/{tabId}/selection/add', body(ids))),
    ),
    remove: useStageMutation(stageId, (ids: string[]) =>
      unwrap(api.POST('/api/stages/{stageId}/tabs/{tabId}/selection/remove', body(ids))),
    ),
    clear: useStageMutation(stageId, () =>
      unwrap(api.POST('/api/stages/{stageId}/tabs/{tabId}/selection/clear', tabPath)),
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

/**
 * 블라인드 위반 의심 해제와 해제 취소. 해제하면 지원자가 리스트의 원래 자리로 돌아가고, 해제 취소하면 맨 아래 블라인드
 * 위반 의심으로 다시 간다
 */
export function useSchoolMentionActions(stageId: string, applicationId: string) {
  const params = { params: { path: { stageId, applicationId } } }
  return {
    clear: useStageMutation(stageId, () =>
      unwrap(api.POST('/api/stages/{stageId}/candidates/{applicationId}/school-clear', params)),
    ),
    undo: useStageMutation(stageId, () =>
      unwrap(api.DELETE('/api/stages/{stageId}/candidates/{applicationId}/school-clear', params)),
    ),
  }
}

/** 결정은 탭과 상관없다. 되돌리기만 누른 탭(tabId)에 없던 지원자를 그 탭에 넣는다 */
export function useDecisionActions(stageId: string, tabId: string) {
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
          body: { applicationIds: ids, tabId },
        }),
      ),
    ),
  }
}

/** 전형 결과 확정. 탭은 남고 탭의 선택 지원자는 비워진다 */
export function useConfirmStage(stageId: string) {
  return useStageMutation(stageId, () =>
    unwrap(api.POST('/api/stages/{stageId}/confirm', path(stageId))),
  )
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

/** 카드의 경력 한 줄: "경력 5년", 신입은 "신입". 분석 전이면 "분석 중" */
export function careerYearsLabel(row: Pick<CandidateRow, 'careerYears' | 'analysisStatus'>) {
  if (row.careerYears === null) {
    if (row.analysisStatus === 'DONE') return '경력 확인 필요'
    return row.analysisStatus === 'FAILED' ? '분석 실패' : '분석 중'
  }
  return row.careerYears === 0 ? '신입' : `경력 ${row.careerYears}년`
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
