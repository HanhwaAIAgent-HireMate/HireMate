import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, expect, it, vi } from 'vitest'

import { useMyInterviews } from './sessions'

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

it('내 면접 목록은 다른 화면에서 면접을 시작해도 주기적으로 상태를 새로 읽는다', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  let status = 'SCHEDULED'
  vi.stubGlobal('fetch', () =>
    Promise.resolve(
      Response.json({
        items: [
          {
            stageId: 'stage',
            applicationId: 'kim',
            recruitmentTitle: '채용',
            stageName: '면접',
            applicantName: '김지원',
            schedule: null,
            myRole: 'HR',
            status,
            recruitmentId: 'recruit',
          },
        ],
        total: 1,
        page: 0,
        size: 50,
      }),
    ),
  )
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const hook = renderHook(() => useMyInterviews(), { wrapper })
  await waitFor(() => expect(hook.result.current.data?.items[0].status).toBe('SCHEDULED'))
  status = 'IN_PROGRESS'
  await act(() => vi.advanceTimersByTimeAsync(5_100))
  expect(hook.result.current.data?.items[0].status).toBe('IN_PROGRESS')
  hook.unmount()
  client.clear()
})
