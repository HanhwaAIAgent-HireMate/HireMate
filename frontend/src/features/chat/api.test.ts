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
    const reply = await act(() =>
      result.current.chat.mutateAsync({
        message: '프로젝트 기반 질문 1개 추가해줘',
        mentionIds: ['a1'],
        checkedIds: [],
      }),
    )
    expect(historyReads).toBe(1)
    // 답과 함께 보낸 때부터 걸린 시간을 돌려준다. 화면은 이 시간을 처리 과정 요약에 쓴다
    expect(reply.answer.selectionChanged).toBe(true)
    expect(reply.seconds).toBeGreaterThanOrEqual(0)
  } finally {
    client.clear()
    resetCsrf()
    vi.unstubAllGlobals()
  }
})

it('화면을 떠나면 요청을 끊고, 끊은 뒤에 온 답으로 화면을 갱신하지 않는다', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  let sent: Request | undefined
  let finish: (() => void) | undefined
  resetCsrf()
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      const requestUrl = typeof input === 'string' ? input : input.url
      if (requestUrl.endsWith('/csrf'))
        return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
      sent = input as Request
      // 서버가 끊긴 요청을 모르고 나중에 done을 보내는 경우
      const body = new ReadableStream<Uint8Array>({
        start(controller) {
          finish = () => {
            const done = JSON.stringify({ ...ANSWER, selectionChanged: true })
            controller.enqueue(new TextEncoder().encode(`event:done\ndata:${done}\n\n`))
            controller.close()
          }
        },
      })
      return Promise.resolve(
        new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
      )
    }),
  )
  try {
    const { result, unmount } = renderHook(
      () => useChat('s1', { onStatus: vi.fn(), onItem: vi.fn() }),
      {
        wrapper: ({ children }: { children: ReactNode }) =>
          createElement(QueryClientProvider, { client }, children),
      },
    )
    let sending: Promise<unknown> | undefined
    act(() => {
      sending = result.current
        .mutateAsync({ message: '강점은?', mentionIds: ['a1'], checkedIds: [] })
        .catch((error: unknown) => error)
    })
    await waitFor(() => expect(finish).toBeDefined())

    unmount()
    finish?.()

    expect(await sending).toMatchObject({ name: 'AbortError' })
    expect(sent?.signal.aborted).toBe(true)
    expect(invalidate).not.toHaveBeenCalled()
  } finally {
    client.clear()
    resetCsrf()
    vi.unstubAllGlobals()
  }
})
