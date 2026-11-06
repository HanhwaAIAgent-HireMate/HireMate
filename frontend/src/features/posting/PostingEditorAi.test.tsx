import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { TooltipProvider } from '@/components/ui/tooltip'
import { postingKeys, type Posting } from '@/features/posting/api'
import { initialPoster } from '@/features/posting/poster-design'
import { resetCsrf } from '@/lib/api/client'
import { PostingEditorPage } from '@/pages/hr/PostingEditorPage'

const posting: Posting = {
  postingId: 'posting-1',
  recruitmentId: 'recruitment-1',
  companyName: '테스트 기업',
  status: 'DRAFT',
  content: {
    title: '마케팅 신입 채용',
    jobCategory: '마케팅',
    career: '신입',
    employmentType: '정규직',
    location: '서울',
    intro: '회사를 소개합니다.',
    duties: ['마케팅 캠페인 운영'],
    qualifications: ['마케팅 기초 지식'],
    preferred: [],
    benefits: ['교육 지원'],
    roles: [],
    blind: false,
    headcount: 3,
    position: '',
    education: '',
    workHours: '',
    salary: '',
  },
  notices: [],
  stages: [],
  documents: [],
  openAt: '2026-11-01T00:00:00Z',
  closeAt: '2026-12-01T00:00:00Z',
  publishedAt: null,
  closedAt: null,
  suggestion: null,
  poster: initialPoster(),
  required: { qualifications: [], preferred: [] },
}

const encoder = new TextEncoder()
const sse = (event: string, data: unknown) =>
  encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)

/** 열어 둔 SSE 응답. 테스트가 이벤트를 보내는 때에 맞춰 흘려 보낸다 */
function openStream() {
  let controller!: ReadableStreamDefaultController<Uint8Array>
  const body = new ReadableStream<Uint8Array>({
    start: (c) => {
      controller = c
    },
  })
  return {
    response: new Response(body, { headers: { 'Content-Type': 'text/event-stream' } }),
    send: (event: string, data: unknown) => controller.enqueue(sse(event, data)),
    close: () => controller.close(),
  }
}

beforeEach(() => {
  resetCsrf()
  sessionStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

function renderEditor(stream: ReturnType<typeof openStream>) {
  const requests: string[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const request =
      typeof input === 'string' ? new Request(new URL(input, 'http://localhost')) : input
    requests.push(`${request.method} ${new URL(request.url).pathname}`)
    if (request.url.endsWith('/csrf'))
      return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (request.method === 'PUT') {
      // 서버는 저장한 본문을 돌려준다. 본문이 바뀌면 편집 화면이 새로 열린다
      const saved = (await request.json()) as Posting['content']
      return Response.json({ ...posting, content: { ...posting.content, title: saved.title } })
    }
    if (request.url.endsWith('/ai-requests')) return stream.response
    throw new Error(`Unexpected request: ${request.method} ${request.url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  const router = createMemoryRouter(
    [{ path: '/hr/recruitments/:recruitmentId/posting', element: <PostingEditorPage /> }],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting`] },
  )
  render(
    <QueryClientProvider client={query}>
      <TooltipProvider>
        <RouterProvider router={router} />
      </TooltipProvider>
    </QueryClientProvider>,
  )
  return requests
}

function ask(message: string) {
  fireEvent.change(screen.getByLabelText('수정할 내용'), { target: { value: message } })
  fireEvent.click(screen.getByRole('button', { name: '보내기' }))
}

describe('공고 AI 수정 요청의 처리 단계', () => {
  it('직접 고친 내용을 저장하고 보낸 요청도 답이 올 때까지 처리 단계를 보인다', async () => {
    const stream = openStream()
    const requests = renderEditor(stream)

    // 직접 고친 내용이 있으면 요청 전에 저장하고, 저장하면 편집 화면이 새로 열린다
    fireEvent.change(screen.getByRole('textbox', { name: '채용명' }), {
      target: { value: '마케팅 경력 채용' },
    })
    ask('백엔드 개발자 10년차 1명 정규직')

    await waitFor(() =>
      expect(requests).toContain('POST /api/recruitments/recruitment-1/posting/ai-requests'),
    )
    expect(requests).toContain('PUT /api/recruitments/recruitment-1/posting')
    await waitFor(() =>
      expect(screen.getByTestId('root-step')).toHaveTextContent('수정안을 만들고 있어요'),
    )

    stream.send('status', { text: '요청을 확인하고 있어요', depth: 0 })
    await waitFor(() =>
      expect(screen.getByTestId('root-step')).toHaveTextContent('요청을 확인하고 있어요'),
    )

    stream.send('done', {
      reply: '수정안을 만들었어요.',
      agent: 'Posting Agent',
      stub: false,
      ncsSources: [],
      posting: { ...posting, content: { ...posting.content, title: '마케팅 경력 채용' } },
    })
    stream.close()
    await screen.findByText('수정안을 만들었어요.')
    expect(screen.getByRole('button', { name: /처리 과정 1단계/ })).toBeInTheDocument()
    expect(screen.queryByTestId('root-step')).not.toBeInTheDocument()
  })

  it('고친 내용이 없어도 같은 처리 단계를 보인다', async () => {
    const stream = openStream()
    const requests = renderEditor(stream)

    ask('백엔드 개발자 10년차 1명 정규직')

    await waitFor(() =>
      expect(screen.getByTestId('root-step')).toHaveTextContent('수정안을 만들고 있어요'),
    )
    stream.send('status', { text: '요청을 확인하고 있어요', depth: 0 })
    await waitFor(() =>
      expect(screen.getByTestId('root-step')).toHaveTextContent('요청을 확인하고 있어요'),
    )
    expect(requests).not.toContain('PUT /api/recruitments/recruitment-1/posting')
    stream.close()
  })
})
