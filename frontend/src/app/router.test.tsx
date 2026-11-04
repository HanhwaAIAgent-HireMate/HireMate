import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
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

function mockServer(loggedIn: boolean, role = 'HR') {
  let authenticated = loggedIn
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      const url = typeof input === 'string' ? input : input.url
      if (url.endsWith('/api/auth/csrf'))
        return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
      if (url.endsWith('/api/auth/signup'))
        return Promise.resolve(new Response(null, { status: 201 }))
      if (url.endsWith('/api/auth/login')) {
        authenticated = true
        return Promise.resolve(Response.json({ ...member, role }))
      }
      if (url.endsWith('/api/auth/me')) {
        return Promise.resolve(
          Response.json(authenticated ? { ...member, role } : { code: 'UNAUTHENTICATED' }, {
            status: authenticated ? 200 : 401,
          }),
        )
      }
      if (url.endsWith('/api/companies/me/profile'))
        return Promise.resolve(Response.json({ name: 'OO핀테크' }))
      return Promise.resolve(Response.json({ code: 'NOT_FOUND' }, { status: 404 }))
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
    ['/', '채용'],
    ['/hr', '채용'],
    ['/hr/settings', '설정'],
    ['/hr/recruitments/1/posting', '공고 편집'],
    ['/hr/recruitments/1/posting/poster', '공고 디자인'],
    ['/hr/recruitments/1/posting/publish', '공고 게시'],
    ['/hr/recruitments/1/posting/status', '공고 · 지원 접수'],
    ['/hr/recruitments/1/stages/2', '공통 전형 화면'],
    ['/hr/recruitments/1/stages/2/close', '전형 종료'],
    ['/hr/recruitments/1/stages/2/close/notices/PASS', '안내 초안'],
    ['/hr/recruitments/1/report', '채용 리포트'],
    ['/careers/1', '채용 공고'],
    ['/careers/1/apply', '지원서'],
  ])('%s 경로는 "%s" 화면을 연다', async (path, title) => {
    mockServer(true)
    renderAt(path)

    expect(await screen.findByRole('heading', { level: 1, name: title })).toBeInTheDocument()
  })

  it('면접관 계정은 HR 화면 대신 면접관 모드의 내 면접으로 보낸다', async () => {
    mockServer(true, 'INTERVIEWER')
    renderAt('/hr/settings')

    expect(await screen.findByRole('heading', { level: 1, name: '내 면접' })).toBeInTheDocument()
    expect(screen.getByText('면접관 모드')).toBeInTheDocument()
  })

  it('HR 계정은 면접관으로 배정하지 않으므로 면접관 모드 대신 HR 콘솔로 보낸다', async () => {
    mockServer(true)
    renderAt('/interviewer')

    expect(await screen.findByRole('heading', { level: 1, name: '채용' })).toBeInTheDocument()
  })

  it('로그인하지 않으면 HR 화면 대신 로그인 화면으로 보낸다', async () => {
    mockServer(false)
    renderAt('/hr/settings')

    expect(await screen.findByRole('heading', { level: 1, name: '로그인' })).toBeInTheDocument()
  })

  it.each(['/login', '/login?next=%2Fhr', '/login?next=%2Fhr%2F'])(
    '%s의 일반 로그인 목적지는 채용 페이지다',
    async (path) => {
      mockServer(true)
      renderAt(path)
      expect(await screen.findByRole('heading', { level: 1, name: '채용' })).toBeInTheDocument()
    },
  )

  it('특정 공고로 이동하던 중 로그인하면 해당 공고로 돌아간다', async () => {
    mockServer(true)
    renderAt('/login?next=%2Fhr%2Frecruitments%2F1%2Fposting')
    expect(await screen.findByRole('heading', { level: 1, name: '공고 편집' })).toBeInTheDocument()
  })

  it('회원가입 직후에는 회사 소개를 작성할 수 있도록 설정 화면을 연다', async () => {
    mockServer(false)
    renderAt('/signup')
    await screen.findByRole('heading', { name: '기업 가입' })
    fireEvent.change(screen.getByLabelText('회사 이름'), { target: { value: '테스트 기업' } })
    fireEvent.change(screen.getByLabelText('담당자 이름'), { target: { value: '최은영' } })
    fireEvent.change(screen.getByLabelText('이메일'), { target: { value: 'hr@example.com' } })
    fireEvent.change(screen.getByLabelText('비밀번호 (12자 이상)'), {
      target: { value: 'test-password-2026' },
    })
    fireEvent.click(screen.getByRole('button', { name: '가입하고 시작하기' }))
    expect(await screen.findByRole('heading', { level: 1, name: '설정' })).toBeInTheDocument()
  })

  it('이후 일반 로그인은 채용 페이지를 연다', async () => {
    mockServer(false)
    renderAt('/login')
    await screen.findByRole('heading', { name: '로그인' })
    fireEvent.change(screen.getByLabelText('이메일'), { target: { value: 'hr@example.com' } })
    fireEvent.change(screen.getByLabelText('비밀번호'), { target: { value: 'test-password-2026' } })
    fireEvent.click(screen.getByRole('button', { name: '로그인' }))
    expect(await screen.findByRole('heading', { level: 1, name: '채용' })).toBeInTheDocument()
  })
})
