import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, Link, RouterProvider } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { HrLayout } from './HrLayout'
import { DashboardPage } from '@/pages/hr/DashboardPage'

beforeEach(() => localStorage.clear())
afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

it.each(['poster', 'publish'] as const)(
  '%s에서 로고로 목록에 나갔다가 카드를 열면 마지막 단계로 돌아온다',
  async (step) => {
    const base = '/hr/recruitments/draft-1/posting'
    vi.stubGlobal('fetch', (input: Request | string) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/auth/me'))
        return Promise.resolve(
          Response.json({
            memberId: 'hr-1',
            companyId: 'company-1',
            role: 'HR',
            name: '담당자',
            email: 'hr@example.com',
          }),
        )
      if (url.endsWith('/api/companies/me/profile'))
        return Promise.resolve(Response.json({ name: '예시 기업' }))
      if (url.endsWith('/api/recruitments'))
        return Promise.resolve(
          Response.json({
            counts: { all: 1, draft: 1, published: 0, inProgress: 0, closed: 0 },
            items: [
              {
                recruitmentId: 'draft-1',
                postingId: 'posting-1',
                title: '마케팅 채용',
                status: 'DRAFT',
                applicantCount: 0,
                closeAt: null,
                currentStageId: null,
                steps: [],
                createdAt: '2026-11-04T00:00:00Z',
              },
            ],
          }),
        )
      return Promise.resolve(Response.json({ code: 'NOT_FOUND' }, { status: 404 }))
    })
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    const router = createMemoryRouter(
      [
        {
          path: '/hr',
          element: <HrLayout />,
          children: [
            { index: true, element: <DashboardPage /> },
            { path: 'recruitments/:recruitmentId/posting', element: <h1>글 작성</h1> },
            {
              path: 'recruitments/:recruitmentId/posting/:step',
              element: (
                <>
                  <h1>편집 중</h1>
                  <Link to={base}>글 작성으로 이전</Link>
                </>
              ),
            },
          ],
        },
      ],
      { initialEntries: [`${base}/${step}`] },
    )
    render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    await screen.findByRole('heading', { name: '편집 중' })
    fireEvent.click(await screen.findByRole('link', { name: '예시 기업' }))
    const card = await screen.findByRole('link', { name: /마케팅 채용 작성 중/ })
    expect(card).toHaveAttribute('href', `${base}/${step}`)
    fireEvent.click(card)
    await waitFor(() => expect(router.state.location.pathname).toBe(`${base}/${step}`))
    fireEvent.click(screen.getByRole('link', { name: '글 작성으로 이전' }))
    await screen.findByRole('heading', { name: '글 작성' })
    fireEvent.click(screen.getByRole('link', { name: '예시 기업' }))
    expect(await screen.findByRole('link', { name: /마케팅 채용 작성 중/ })).toHaveAttribute(
      'href',
      base,
    )
  },
)
