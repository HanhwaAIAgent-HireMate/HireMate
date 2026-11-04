import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { postingKeys, type Posting } from '@/features/posting/api'
import { initialPoster } from '@/features/posting/poster-design'
import { resetCsrf } from '@/lib/api/client'
import { PostingPublishPage } from '@/pages/hr/PostingPublishPage'

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
    headcount: 3,
    position: '',
    education: '',
    workHours: '',
    salary: '',
  },
  notices: [],
  stages: [],
  documents: [],
  openAt: null,
  closeAt: null,
  publishedAt: null,
  closedAt: null,
  suggestion: null,
  poster: initialPoster(),
  required: { qualifications: [], preferred: [] },
}

// 2026-11-04 10:00 (로컬 시간)
const NOW = new Date(2026, 10, 4, 10, 0)

beforeEach(() => {
  resetCsrf()
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(NOW)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

function publishPage() {
  const sent: { openAt: string; closeAt: string }[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && input.method === 'POST' && url.endsWith('/publish')) {
      sent.push((await input.json()) as { openAt: string; closeAt: string })
      return Response.json({ ...posting, status: 'PUBLISHED' })
    }
    return Response.json({ code: 'NOT_FOUND' }, { status: 404 })
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  const router = createMemoryRouter(
    [
      { path: '/hr/recruitments/:recruitmentId/posting/publish', element: <PostingPublishPage /> },
      { path: '/hr/recruitments/:recruitmentId/posting/status', element: <p>게시 현황</p> },
    ],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting/publish`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { sent }
}

describe('접수 기간', () => {
  it('지금보다 앞선 시간은 고를 수 없게 한다', () => {
    publishPage()
    expect(screen.getByLabelText('접수 시작')).toHaveAttribute('min', '2026-11-04T10:00')
    expect(screen.getByLabelText('접수 마감')).toHaveAttribute('min', '2026-11-04T11:00')
  })

  it('마감이 지났으면 게시할 수 없고 이유를 알린다', () => {
    publishPage()
    fireEvent.change(screen.getByLabelText('접수 시작'), { target: { value: '2026-11-01T09:00' } })
    fireEvent.change(screen.getByLabelText('접수 마감'), { target: { value: '2026-11-03T18:00' } })
    expect(screen.getByRole('button', { name: '글 공고 게시' })).toBeDisabled()
    expect(screen.getByText('접수 마감은 시작보다 늦고, 지금보다 뒤여야 해요.')).toBeInTheDocument()
  })

  it('이미 지난 시작 시간은 게시한 때로 보낸다', async () => {
    const { sent } = publishPage()
    fireEvent.change(screen.getByLabelText('접수 시작'), { target: { value: '2026-11-01T09:00' } })
    fireEvent.change(screen.getByLabelText('접수 마감'), { target: { value: '2026-11-20T18:00' } })
    fireEvent.click(screen.getByRole('button', { name: '글 공고 게시' }))
    fireEvent.click(screen.getByRole('button', { name: '게시' }))
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0]).toEqual({
      openAt: NOW.toISOString(),
      closeAt: new Date(2026, 10, 20, 18, 0).toISOString(),
    })
  })
})
