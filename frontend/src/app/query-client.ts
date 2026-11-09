import { QueryClient } from '@tanstack/react-query'

import { ApiError } from '@/lib/api/client'

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // 인터넷이 끊겨도 멈춰 기다리지 않고 요청을 보내 실패를 알린다 (기본 'online'은 조용히 멈춘다)
        networkMode: 'always',
        staleTime: 30 * 1000,
        refetchOnWindowFocus: false,
        // 4xx는 다시 시도해도 같은 결과라 바로 실패로 둔다
        retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
      },
      // 버튼으로 보내는 요청도 인터넷이 끊기면 멈추지 않고 바로 실패해 오류 안내가 뜨게 한다
      mutations: { networkMode: 'always' },
    },
  })
}
