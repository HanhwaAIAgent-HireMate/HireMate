import { describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook, waitFor } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'

import { madeQuestions, readChat, useChat, useChatHistory } from '@/features/chat/api'
import { ApiError, resetCsrf } from '@/lib/api/client'
import { streamOf } from '@/test/stream'

const ANSWER = {
  intent: 'ANSWER',
  mode: null,
  message: '비교했어요.',
  items: [],
  sources: [],
  agents: [],
  selectionChanged: false,
  stub: false,
}

describe('readChat', () => {
  it('진행 알림을 차례로 넘기고 done의 답을 돌려준다', async () => {
    const onStatus = vi.fn()
    const onItem = vi.fn()
    const item = { applicationId: 'a1', label: 'RDBMS', text: 'Oracle 원장 설계', status: 'OK' }

    const answer = await readChat(
      streamOf(
        'event:status\ndata:{"text":"2명 자료를 정리하고 있어요"}\n\n',
        `event:item\ndata:${JSON.stringify(item)}\n\n`,
        `event:done\ndata:${JSON.stringify(ANSWER)}\n\n`,
      ),
      { onStatus, onItem },
    )

    expect(onStatus).toHaveBeenCalledWith('2명 자료를 정리하고 있어요')
    expect(onItem).toHaveBeenCalledWith(item)
    expect(answer).toEqual(ANSWER)
  })

  it('error 이벤트는 상태와 code를 담은 ApiError로 던진다', async () => {
    const reading = readChat(
      streamOf('event:error\ndata:{"status":502,"code":"AI_UNAVAILABLE"}\n\n'),
      { onStatus: vi.fn(), onItem: vi.fn() },
    )

    await expect(reading).rejects.toEqual(new ApiError(502, 'AI_UNAVAILABLE', ''))
    await expect(reading).rejects.toBeInstanceOf(ApiError)
  })

  it('done 없이 끝나면 AI_UNAVAILABLE로 던진다', async () => {
    const reading = readChat(streamOf('event:status\ndata:{"text":"a"}\n\n'), {
      onStatus: vi.fn(),
      onItem: vi.fn(),
    })

    await expect(reading).rejects.toMatchObject({ status: 502, code: 'AI_UNAVAILABLE' })
  })
})

describe('madeQuestions', () => {
  it('Interview Agent가 답했을 때만 카드 질문을 다시 불러온다', () => {
    expect(madeQuestions({ agents: ['Interview Agent'] })).toBe(true)
    expect(madeQuestions({ agents: ['Root Agent', 'Interview Agent'] })).toBe(true)
    expect(madeQuestions({ agents: ['Application Agent'] })).toBe(false)
    expect(madeQuestions({ agents: [] })).toBe(false)
  })
})

it('선택 목록을 갱신해도 방금 보낸 대화를 빈 과거 기록으로 덮어쓰지 않는다', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let historyReads = 0
  resetCsrf()
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      const requestUrl = typeof input === 'string' ? input : input.url
      if (requestUrl.endsWith('/csrf'))
        return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
      if (typeof input !== 'string' && input.method === 'POST')
        return Promise.resolve(
          new Response(
            streamOf(
              `event:done\ndata:${JSON.stringify({ ...ANSWER, selectionChanged: true })}\n\n`,
            ),
            { headers: { 'Content-Type': 'text/event-stream' } },
          ),
        )
      historyReads++
      return Promise.resolve(Response.json([]))
    }),
  )
  try {
    const { result } = renderHook(
      () => ({
        history: useChatHistory('s1'),
        chat: useChat('s1', { onStatus: vi.fn(), onItem: vi.fn() }),
      }),
      {
        wrapper: ({ children }: { children: ReactNode }) =>
          createElement(QueryClientProvider, { client }, children),
      },
    )
    await waitFor(() => expect(result.current.history.isSuccess).toBe(true))
    await act(() =>
      result.current.chat.mutateAsync({
        message: '프로젝트 기반 질문 1개 추가해줘',
        mentionIds: ['a1'],
        checkedIds: [],
      }),
    )
    expect(historyReads).toBe(1)
  } finally {
    client.clear()
    resetCsrf()
    vi.unstubAllGlobals()
  }
})
