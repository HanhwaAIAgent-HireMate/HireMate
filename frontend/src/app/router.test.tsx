import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from './query-client'
import { routes } from './router'

const member = {
  memberId: 'm1',
  companyId: 'c1',
  name: '최은영',
  email: 'hr@example.com',
  role: 'HR',
}

function mockServer(loggedIn: boolean) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/auth/me')) {
        return Promise.resolve(
          Response.json(loggedIn ? member : { code: 'UNAUTHENTICATED' }, {
            status: loggedIn ? 200 : 401,
          }),
        )
      }
      return Promise.resolve(Response.json({ name: 'OO핀테크' }))
    }),
  )
}

function renderAt(path: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(routes, { initialEntries: [path] })} />
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('routes', () => {
  it.each([
    ['/', '채용 대시보드'],
    ['/hr', '채용 대시보드'],
    ['/hr/settings', '설정'],
    ['/hr/recruitments/new', '공고 편집'],
    ['/hr/recruitments/1/posting', '공고 편집'],
    ['/hr/recruitments/1/stages/2', '공통 전형 화면'],
    ['/hr/recruitments/1/stages/2/close', '전형 종료'],
    ['/hr/recruitments/1/report', '채용 리포트'],
    ['/careers/1', '채용 공고'],
    ['/careers/1/apply', '지원서'],
  ])('%s 경로는 "%s" 화면을 연다', async (path, title) => {
    mockServer(true)
    renderAt(path)

    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
  })

  it('로그인하지 않으면 HR 화면 대신 로그인 화면으로 보낸다', async () => {
    mockServer(false)
    renderAt('/hr/settings')

    expect(await screen.findByRole('heading', { level: 1, name: '로그인' })).toBeInTheDocument()
  })
})
