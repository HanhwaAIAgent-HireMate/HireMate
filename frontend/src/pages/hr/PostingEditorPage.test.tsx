import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, MemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { postingKeys, type Posting, type PublicPosting } from '@/features/posting/api'
import { CareersPosting } from '@/features/posting/CareersPosting'
import { posterBrandKey } from '@/features/posting/poster-api'
import { initialPoster, type PosterDesign } from '@/features/posting/poster-design'
import { resetCsrf } from '@/lib/api/client'
import { PostingEditorPage } from '@/pages/hr/PostingEditorPage'
import { PostingPosterPage } from '@/pages/hr/PostingPosterPage'

// 편집기 내부 저장은 기존 동작이며, 여기서는 저장 이후의 형식 선택과 이동을 검사한다.
vi.mock('@/features/posting/PostingEditor', () => ({
  PostingEditor: ({ onNext }: { onNext: () => void }) => <button onClick={onNext}>다음</button>,
}))

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
  notices: ['지원 내용을 확인해 주세요.'],
  stages: [],
  documents: [],
  openAt: '2026-11-01T00:00:00Z',
  closeAt: '2026-12-01T00:00:00Z',
  publishedAt: null,
  closedAt: null,
  suggestion: null,
  poster: { ...initialPoster(), enabled: true, color: '#116644' },
  required: { qualifications: [], preferred: [] },
}

beforeEach(() => {
  resetCsrf()
  sessionStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

function editor(fail = false) {
  const saved: PosterDesign[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && input.method === 'PUT') {
      const design = (await input.json()) as PosterDesign
      saved.push(design)
      return fail
        ? Response.json({ code: 'SAVE_FAILED' }, { status: 500 })
        : Response.json({ ...posting, poster: design })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  query.setQueryData(posterBrandKey, {})
  const router = createMemoryRouter(
    [
      { path: '/hr/recruitments/:recruitmentId/posting', element: <PostingEditorPage /> },
      { path: '/hr/recruitments/:recruitmentId/posting/:step', element: <p>다음 화면</p> },
    ],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: '다음' }))
  return { router, saved }
}

describe('게시 형식 선택', () => {
  it.each([
    ['글 공고 선택', false, 'publish'],
    ['포스터 공고 선택', true, 'poster'],
  ] as const)('%s을 저장한 뒤 해당 단계로 이동한다', async (label, enabled, step) => {
    const { router, saved } = editor()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '선택' })).toBeDisabled()
    expect(screen.getAllByText(posting.content.title)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: label }))
    fireEvent.click(screen.getByRole('button', { name: '선택' }))
    await waitFor(() => expect(router.state.location.pathname).toMatch(new RegExp(`/${step}$`)))
    expect(saved).toEqual([{ ...posting.poster, enabled }])
  })

  it('취소하면 이동하거나 저장하지 않는다', () => {
    const { router, saved } = editor()
    fireEvent.click(screen.getByRole('button', { name: '취소' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(router.state.location.pathname).toMatch(/\/posting$/)
    expect(saved).toEqual([])
  })

  it('형식 저장이 실패하면 선택 창을 유지한다', async () => {
    const { router, saved } = editor(true)
    fireEvent.click(screen.getByRole('button', { name: '글 공고 선택' }))
    fireEvent.click(screen.getByRole('button', { name: '선택' }))
    await waitFor(() => expect(saved).toHaveLength(1))
    await waitFor(() => expect(screen.getByRole('button', { name: '선택' })).toBeEnabled())
    expect(router.state.location.pathname).toMatch(/\/posting$/)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('선택한 형식의 채용 페이지', () => {
  it.each([false, true])('포스터 사용 %s일 때 본문을 중복 표시하지 않는다', (enabled) => {
    const publicPosting: PublicPosting = {
      ...posting,
      openAt: posting.openAt!,
      closeAt: posting.closeAt!,
      state: 'OPEN',
      companyAddress: '서울 본사',
      poster: { ...initialPoster(), enabled },
    }
    const { container } = render(
      <MemoryRouter>
        <CareersPosting posting={publicPosting} applyPath="/apply" />
      </MemoryRouter>,
    )
    expect(container.querySelector('.posting-poster') !== null).toBe(enabled)
    expect(screen.getAllByText(/마케팅 캠페인 운영/)).toHaveLength(1)
    expect(container.querySelector('#company')).toHaveTextContent(posting.content.intro)
    expect(container.querySelector('#benefits')).toHaveTextContent('교육 지원')
    expect(screen.queryByRole('button', { name: 'PDF 내보내기' }) !== null).toBe(enabled)
    expect(screen.getByRole('link', { name: '지원하기' })).toHaveAttribute('href', '/apply')
  })
})

it('포스터 대화를 지우면 복구 기록과 다음 요청의 대화는 비우고 디자인은 유지한다', async () => {
  const key = `hiremate:posting:${posting.recruitmentId}:poster-chat`
  sessionStorage.setItem(
    key,
    JSON.stringify({
      baseline: '[]',
      value: [
        { role: 'USER', text: '이전 요청', design: null, recommendations: [] },
        { role: 'ASSISTANT', text: '이전 답변', design: null, recommendations: [] },
      ],
    }),
  )
  let request: { history: unknown[]; design: PosterDesign } | undefined
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && url.endsWith('/ai-requests')) {
      request = (await input.json()) as { history: unknown[]; design: PosterDesign }
      return Response.json({ reply: '새 답변', recommendations: [] })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  query.setQueryData(posterBrandKey, {})
  const router = createMemoryRouter(
    [{ path: '/hr/recruitments/:recruitmentId/posting/poster', element: <PostingPosterPage /> }],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting/poster`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  expect(screen.getByText('이전 답변')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '대화 지우기' }))
  expect(screen.queryByText('이전 답변')).not.toBeInTheDocument()
  expect(screen.queryByText('이전 요청')).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).toBeNull()
  expect(screen.getByLabelText('대표 색상')).toHaveValue(posting.poster!.color)
  fireEvent.click(screen.getByRole('button', { name: '우리는 더 고급스러운 느낌이 있어야 해' }))
  await screen.findByText('새 답변')
  expect(request?.history).toEqual([])
  expect(request?.design).toEqual(posting.poster)
})
