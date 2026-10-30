import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import type { PropsWithChildren } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useInterview, useInterviewPreparing } from './api'

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  return { client, wrapper }
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('지원자별 면접 질문 갱신', () => {
  it('처음에는 대기열에 없어도 다시 확인하고 한 명의 질문부터 갱신한다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const preparing = new Map([
      ['kim', false],
      ['lee', true],
    ])
    const ready = new Set<string>()
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) => {
        const id = request.url.includes('/kim/') ? 'kim' : 'lee'
        if (request.url.endsWith('/preparing'))
          return Promise.resolve(Response.json({ preparing: preparing.get(id) }))
        return Promise.resolve(
          Response.json({
            applicationId: id,
            schedule: null,
            previous: [],
            singleInterview: true,
            questions: ready.has(id)
              ? [{ questionId: id, text: id + ' 질문', source: 'AI', answer: '', reason: null }]
              : [],
          }),
        )
      }),
    )
    const { client, wrapper } = setup()
    const kim = renderHook(
      () => ({
        interview: useInterview('stage', 'kim'),
        status: useInterviewPreparing('stage', 'kim'),
      }),
      { wrapper },
    )
    const lee = renderHook(
      () => ({
        interview: useInterview('stage', 'lee'),
        status: useInterviewPreparing('stage', 'lee'),
      }),
      { wrapper },
    )
    await waitFor(() => expect(kim.result.current.status.data?.preparing).toBe(false))
    await waitFor(() => expect(lee.result.current.status.data?.preparing).toBe(true))
    preparing.set('kim', true)
    await act(() => vi.advanceTimersByTimeAsync(3100))
    expect(kim.result.current.status.data?.preparing).toBe(true)
    ready.add('kim')
    preparing.set('kim', false)
    await act(() => vi.advanceTimersByTimeAsync(3100))
    expect(kim.result.current.interview.data?.questions[0]?.text).toBe('kim 질문')
    expect(lee.result.current.status.data?.preparing).toBe(true)
    expect(lee.result.current.interview.data?.questions).toHaveLength(0)
    client.clear()
  })

  it('생성 중 상태를 놓쳐도 완료된 질문을 다시 읽는다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((request: Request) =>
        Promise.resolve(
          Response.json(
            request.url.endsWith('/preparing')
              ? { preparing: false }
              : {
                  applicationId: 'kim',
                  schedule: null,
                  previous: [],
                  singleInterview: true,
                  questions: [
                    { questionId: 'q', text: '완료 질문', source: 'AI', answer: '', reason: null },
                  ],
                },
          ),
        ),
      ),
    )
    const { client, wrapper } = setup()
    client.setQueryData(['stage', 'stage', 'interview', 'kim'], { questions: [] })
    const hook = renderHook(
      () => ({
        interview: useInterview('stage', 'kim'),
        status: useInterviewPreparing('stage', 'kim'),
      }),
      { wrapper },
    )
    await waitFor(() =>
      expect(hook.result.current.interview.data?.questions[0]?.text).toBe('완료 질문'),
    )
    client.clear()
  })
})
