import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { CanvaConnection } from './CanvaConnection'

afterEach(() => vi.unstubAllGlobals())

function setup(configured: boolean, connected: boolean) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        Response.json({
          configured,
          connected,
          tools: [],
          redirectUri: 'http://localhost:5173/api/companies/me/canva/callback',
        }),
      ),
    ),
  )
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <CanvaConnection />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

it('서버 설정이 없으면 연결을 허용하지 않고 설정 필요를 안내한다', async () => {
  setup(false, false)
  expect(await screen.findByRole('button', { name: 'Canva 계정 연결' })).toBeDisabled()
  expect(screen.getByText('Canva를 연결하려면 먼저 서버 연결 설정이 필요해요.')).toBeInTheDocument()
})

it('연결 상태를 확인한 계정에만 연결 확인과 해제 버튼을 보여준다', async () => {
  setup(true, true)
  expect(await screen.findByText('연결됨')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '연결 확인' })).toBeEnabled()
  expect(screen.getByRole('button', { name: '연결 해제' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Canva 계정 연결' })).not.toBeInTheDocument()
})
