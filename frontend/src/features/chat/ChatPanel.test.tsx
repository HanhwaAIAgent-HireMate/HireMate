import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '@/features/chat/ChatPanel'
import { useChatStore } from '@/features/chat/store'
import type { StageOverview } from '@/features/screening/api'
import { resetCsrf } from '@/lib/api/client'

const overview = {
  stageId: 's1',
  name: '서류 전형',
  type: 'DOCUMENT',
  counts: { pending: 3, pass: 0, fail: 0, total: 3 },
} as StageOverview

const ANSWER = {
  intent: 'ANSWER',
  mode: null,
  message: '금융 경험이 있는 지원자는 2명이에요.',
  items: [],
  sources: [],
  agents: [],
  selectionChanged: false,
  stub: false,
}

/** 답(done)을 테스트가 보낼 때까지 열어 두는 Chat 서버 */
function mockServer() {
  let finish: (() => void) | undefined
  let answered = false
  const asked: string[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      const url = typeof input === 'string' ? input : input.url
      const method = typeof input === 'string' ? 'GET' : input.method
      const path = new URL(url, 'http://localhost').pathname
      if (path === '/api/auth/csrf')
        return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
      if (method === 'POST' && path.endsWith('/chat')) {
        asked.push(path)
        const body = new ReadableStream<Uint8Array>({
          start(controller) {
            finish = () => {
              answered = true
              const done = JSON.stringify(ANSWER)
              controller.enqueue(new TextEncoder().encode(`event:done\ndata:${done}\n\n`))
              controller.close()
            }
          },
        })
        return Promise.resolve(
          new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
        )
      }
      if (path === '/api/stages/s1/tabs/t1/chat' && answered)
        return Promise.resolve(
          Response.json([
            { message: '금융 경험 찾아줘', mentions: [], answer: ANSWER, steps: [], seconds: 1 },
          ]),
        )
      return Promise.resolve(Response.json([]))
    }),
  )
  return { asked, finish: () => finish?.() }
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrap = (children: ReactNode) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  )
  const view = render(wrap(<ChatPanel overview={overview} tabId="t1" />))
  return {
    show: (tabId: string) => view.rerender(wrap(<ChatPanel overview={overview} tabId={tabId} />)),
  }
}

beforeAll(() => {
  // jsdom에는 화면 스크롤이 없다
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  useChatStore.setState({ threads: {} })
  resetCsrf()
  vi.unstubAllGlobals()
})

describe('ChatPanel', () => {
  it('탭의 대화방으로 묻고, 답을 기다리는 동안 다른 탭으로 옮겨도 답은 물은 탭에 쌓인다', async () => {
    const server = mockServer()
    const panel = renderPanel()
    const input = screen.getByRole('textbox', { name: 'AI Chat 입력' })
    await waitFor(() => expect(screen.getByRole('button', { name: '보내기' })).toBeInTheDocument())

    fireEvent.change(input, { target: { value: '금융 경험 찾아줘' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    await waitFor(() => expect(server.asked).toEqual(['/api/stages/s1/tabs/t1/chat']))

    panel.show('t2')
    expect(screen.queryByText('금융 경험 찾아줘')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'AI Chat 입력' })).toHaveAttribute(
      'placeholder',
      '다른 탭에서 답을 기다리고 있어요',
    )

    server.finish()
    await waitFor(() => expect(useChatStore.getState().threads.t1).toHaveLength(2))
    expect(screen.queryByText(ANSWER.message)).not.toBeInTheDocument()

    panel.show('t1')
    expect(await screen.findByText(ANSWER.message)).toBeInTheDocument()
    expect(screen.getByText('금융 경험 찾아줘')).toBeInTheDocument()
  })

  it('[대화 지우기] 버튼이 없다. 대화는 탭을 지울 때 지운다', async () => {
    mockServer()
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: '보내기' })).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: '대화 지우기' })).not.toBeInTheDocument()
  })
})
