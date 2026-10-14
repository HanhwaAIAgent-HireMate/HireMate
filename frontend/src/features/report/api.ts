import { useQuery } from '@tanstack/react-query'

import { api, ApiError, unwrap } from '@/lib/api/client'

/** 최종 리포트. 채용을 종료한 직후에는 Report Agent가 쓰는 중이라 잠시 뒤 다시 불러온다. */
export function useReport(recruitmentId: string) {
  return useQuery({
    queryKey: ['report', recruitmentId],
    queryFn: () =>
      unwrap(
        api.GET('/api/recruitments/{recruitmentId}/report', {
          params: { path: { recruitmentId } },
        }),
      ),
    retry: (count, error) =>
      error instanceof ApiError && error.code === 'REPORT_NOT_READY' && count < 20,
    retryDelay: 1500,
  })
}
