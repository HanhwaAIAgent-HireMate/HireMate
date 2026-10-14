import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/lib/api/client'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30 * 1000,
        refetchOnWindowFocus: false,
        // 4xx는 다시 시도해도 같은 결과라 바로 실패로 둔다
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
    },
  })
}
