import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { ChatPanel } from '@/features/chat/ChatPanel'
import { useChatStore } from '@/features/chat/store'
import { stageKeys, type StageOverview } from '@/features/screening/api'
import { useStageTabs } from '@/features/screening/tabs'
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

  it('질문에 질문한 담당자 이름을 붙이고, 첫 답 뒤에 온 탭 제목으로 탭 이름을 바꾼다', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: Request | string) => {
        const url = typeof input === 'string' ? input : input.url
        const method = typeof input === 'string' ? 'GET' : input.method
        const path = new URL(url, 'http://localhost').pathname
        if (path === '/api/auth/csrf')
          return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
        if (path === '/api/auth/me') return Promise.resolve(Response.json({ name: '최은영' }))
        if (method === 'POST')
          return Promise.resolve(
            new Response(
              `event:done\ndata:${JSON.stringify(ANSWER)}\n\n` +
                'event:title\ndata:{"tabId":"t1","name":"금융 경험 찾기"}\n\n',
              { headers: { 'Content-Type': 'text/event-stream' } },
            ),
          )
        return Promise.resolve(Response.json([]))
      }),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    client.setQueryData(stageKeys.tabs('s1'), [
      { id: 't1', name: '탭 1', selectedCount: 0 },
      { id: 't2', name: '탭 2', selectedCount: 0 },
    ])
    render(
      <QueryClientProvider client={client}>
        <ChatPanel overview={overview} tabId="t1" />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(client.getQueryData(['auth', 'me'])).toBeTruthy())

    const input = screen.getByRole('textbox', { name: 'AI Chat 입력' })
    fireEvent.change(input, { target: { value: '금융 경험 찾아줘' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)

    expect(await screen.findByText(ANSWER.message)).toBeInTheDocument()
    expect(screen.getByText('최은영')).toBeInTheDocument()
    await waitFor(() =>
      expect(
        client.getQueryData<{ name: string }[]>(stageKeys.tabs('s1'))?.map((tab) => tab.name),
      ).toEqual(['금융 경험 찾기', '탭 2']),
    )
  })

  it('선택 지원자가 바뀐 답 뒤에 늦게 온 탭 목록이 자동 제목을 예전 이름으로 덮어쓰지 않는다', async () => {
    const named = [
      { id: 't1', name: '금융 경험 찾기', selectedCount: 2 },
      { id: 't2', name: '탭 2', selectedCount: 0 },
    ]
    let staleTabs: ((response: Response) => void) | undefined
    let tabReads = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((input: Request | string) => {
        const url = typeof input === 'string' ? input : input.url
        const method = typeof input === 'string' ? 'GET' : input.method
        const path = new URL(url, 'http://localhost').pathname
        if (path === '/api/auth/csrf')
          return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
        if (path === '/api/stages/s1/tabs') {
          tabReads++
          // 답 직후 다시 받는 탭 목록은 제목을 저장하기 전의 이름으로 늦게 온다
          if (tabReads === 2) return new Promise<Response>((resolve) => (staleTabs = resolve))
          return Promise.resolve(
            Response.json(tabReads === 1 ? [{ ...named[0], name: '탭 1' }, named[1]] : named),
          )
        }
        if (method === 'POST')
          return Promise.resolve(
            new Response(
              `event:done\ndata:${JSON.stringify({ ...ANSWER, selectionChanged: true })}\n\n` +
                'event:title\ndata:{"tabId":"t1","name":"금융 경험 찾기"}\n\n',
              { headers: { 'Content-Type': 'text/event-stream' } },
            ),
          )
        return Promise.resolve(Response.json([]))
      }),
    )
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    function TabNames() {
      const tabs = useStageTabs('s1')
      return <p data-testid="tabs">{tabs.data?.map((tab) => tab.name).join(',')}</p>
    }
    render(
      <QueryClientProvider client={client}>
        <TabNames />
        <ChatPanel overview={overview} tabId="t1" />
      </QueryClientProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('tabs')).toHaveTextContent('탭 1,탭 2'))

    const input = screen.getByRole('textbox', { name: 'AI Chat 입력' })
    fireEvent.change(input, { target: { value: '금융 경험 찾아줘' } })
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    await waitFor(() => expect(staleTabs).toBeDefined())
    await waitFor(() => expect(screen.getByTestId('tabs')).toHaveTextContent('금융 경험 찾기,탭 2'))
    staleTabs?.(Response.json([{ ...named[0], name: '탭 1' }, named[1]]))

    await waitFor(() => expect(tabReads).toBeGreaterThanOrEqual(3))
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.getByTestId('tabs')).toHaveTextContent('금융 경험 찾기,탭 2')
  })

  it('[대화 지우기] 버튼이 없다. 대화는 탭을 지울 때 지운다', async () => {
    mockServer()
    renderPanel()
    await waitFor(() => expect(screen.getByRole('button', { name: '보내기' })).toBeInTheDocument())

    expect(screen.queryByRole('button', { name: '대화 지우기' })).not.toBeInTheDocument()
  })
})
