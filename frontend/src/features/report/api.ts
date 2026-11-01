import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api, unwrap, type Schemas } from '@/lib/api/client'

import type { ReportBundle, ReportSpec, ReportView } from './types'

/** 채용 종료 직후 최종 리포트가 목록에 생길 때까지 이 간격으로 다시 불러온다 */
const REPORT_POLL_MS = 5000

export type ReportPayload = Schemas['ReportPayload']

/** Report Agent 리포트(전형 결과 · 지원자 비교)를 쓰는 동안 다시 묻는 간격 */
const AGENT_REPORT_POLL_MS = 3000

/** 리포트 한 건. 쓰는 중(PENDING)이면 다 쓸 때까지 다시 불러온다. 같은 채용이면 다른 전형 화면에서도 연다 */
export function useAgentReport(stageId: string, reportId: string | null) {
  return useQuery({
    queryKey: ['agent-report', stageId, reportId],
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/reports/{reportId}', {
          params: { path: { stageId, reportId: reportId ?? '' } },
        }),
      ),
    enabled: reportId !== null,
    refetchInterval: (query) =>
      query.state.data?.status === 'PENDING' ? AGENT_REPORT_POLL_MS : false,
  })
}

/** 선택 지원자 비교 리포트 요청. Root Agent를 거치지 않고 바로 Report Agent에 맡긴다 */
export function useRequestCompareReport(stageId: string) {
  return useMutation({
    mutationFn: (request: { applicationIds: string[]; focus: string; brief: boolean }) =>
      unwrap(
        api.POST('/api/stages/{stageId}/reports/compare', {
          params: { path: { stageId } },
          body: request,
        }),
      ),
  })
}

export type ReportDistribution = Schemas['ReportDistribution']
export type DistributionSort = ReportDistribution['sort']

/**
 * 서류 전형 분포. backend가 모델 없이 바로 센다. 목표 인원(target)은 저장하지 않고 요청마다 넘긴다.
 * 목표를 바꾸는 동안 앞 결과를 그대로 보여 준다
 */
export function useReportDistribution(
  stageId: string,
  target: number | null,
  sort: DistributionSort,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['report-distribution', stageId, target, sort],
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/reports/distribution', {
          params: { path: { stageId }, query: { target: target ?? undefined, sort } },
        }),
      ),
    enabled,
    placeholderData: keepPreviousData,
  })
}

export type ReportSummary = Schemas['ReportSummary']

/** 전형의 전형 결과 리포트 목록. 최근 것이 먼저고, 쓰는 중인 리포트가 있으면 다 쓸 때까지 다시 묻는다 */
export function useStageReports(stageId: string) {
  return useQuery({
    queryKey: ['stage-reports', stageId],
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/reports', {
          params: { path: { stageId } },
        }),
      ),
    refetchInterval: (query) =>
      query.state.data?.some((report) => report.status === 'PENDING')
        ? AGENT_REPORT_POLL_MS
        : false,
  })
}

/** 전형 결과 리포트를 연다. 저장된 것이 있으면 그 ID를, 없으면 결과를 확정한 전형만 새로 만든다 */
export function useOpenStageReport(stageId: string) {
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/stages/{stageId}/reports/stage', {
          params: { path: { stageId } },
        }),
      ),
  })
}

/** 채용 최종 리포트 목록. 채용을 종료한 직후에는 Report Agent가 쓰기 시작하기 전이라 비어 있으면 다시 묻는다 */
export function useFinalReports(recruitmentId: string, closed: boolean) {
  return useQuery({
    queryKey: ['final-reports', recruitmentId],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/reports', {
          params: { path: { recruitmentId } },
        }),
      ),
    refetchInterval: (query) => (closed && query.state.data?.length === 0 ? REPORT_POLL_MS : false),
  })
}

/** 채용 최종 리포트를 연다. 없거나 실패했으면 종료한 채용만 새로 만든다 */
export function useOpenFinalReport(recruitmentId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () =>
      unwrap(
        api.POST('/api/recruitments/{recruitmentId}/reports/final', {
          params: { path: { recruitmentId } },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: ['final-reports', recruitmentId] }),
  })
}

/**
 * 화면이 그릴 리포트. 다 쓰기 전이거나 실패했으면 null이다.
 * 묶음과 설계서는 ai contract(ReportBundle · ReportSpec) 모양 그대로 backend가 넘긴 JSON이다.
 */
export function toReportView(payload: ReportPayload): ReportView | null {
  if (!payload.report) return null
  return {
    bundle: payload.bundle as unknown as ReportBundle,
    spec: payload.report.spec as unknown as ReportSpec,
    names: payload.names,
    skills: payload.report.skills,
    specialists: payload.report.specialists,
    fallback: payload.report.fallback,
  }
}
