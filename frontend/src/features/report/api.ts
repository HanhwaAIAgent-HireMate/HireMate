import { useQuery } from '@tanstack/react-query'

import { api, ApiError, unwrap } from '@/lib/api/client'

/** Report Agent가 리포트를 쓰는 동안 이 간격으로 다시 불러온다. AI 워커가 대기열에서 처리해 몇 분 걸릴 수 있다 */
const REPORT_POLL_MS = 5000

/** 리포트를 아직 쓰는 중인가 (REPORT_NOT_READY) */
export function reportNotReady(error: unknown) {
  return error instanceof ApiError && error.code === 'REPORT_NOT_READY'
}

/** 최종 리포트. 채용을 종료한 직후에는 Report Agent가 쓰는 중이라 준비될 때까지 다시 불러온다. */
export function useReport(recruitmentId: string) {
  return useQuery({
    queryKey: ['report', recruitmentId],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/report', {
          params: { path: { recruitmentId } },
        }),
      ),
    retry: (count, error) => !reportNotReady(error) && count < 3,
    refetchInterval: (query) => (reportNotReady(query.state.error) ? REPORT_POLL_MS : false),
  })
}
