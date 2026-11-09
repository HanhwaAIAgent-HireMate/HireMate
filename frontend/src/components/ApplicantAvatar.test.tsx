import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { StrictMode } from 'react'

import { ApplicantAvatar } from '@/components/ApplicantAvatar'

afterEach(() => vi.unstubAllGlobals())

it('테스트 사진을 별도 문구 없이 표시한다', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(new Blob(['example']), {
          status: 200,
          headers: { 'X-Example-Photo': 'true' },
        }),
      ),
    ),
  )
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:example-photo'),
      revokeObjectURL: vi.fn(),
    }),
  )
  const { container } = render(
    <QueryClientProvider client={new QueryClient()}>
      <ApplicantAvatar recruitmentId="recruitment" applicationId="applicant" />
    </QueryClientProvider>,
  )
  await waitFor(() =>
    expect(container.querySelector('img')).toHaveAttribute('src', 'blob:example-photo'),
  )
  expect(screen.queryByText('예시 사진')).not.toBeInTheDocument()
})

it('저장된 지원자 사진을 담당자에게 보여 준다', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(new Blob(['photo']), { status: 200 }))),
  )
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:stored-photo'),
      revokeObjectURL: vi.fn(),
    }),
  )
  const { container } = render(
    <QueryClientProvider client={new QueryClient()}>
      <ApplicantAvatar recruitmentId="recruitment" applicationId="applicant" />
    </QueryClientProvider>,
  )
  await waitFor(() =>
    expect(container.querySelector('img')).toHaveAttribute('src', 'blob:stored-photo'),
  )
})

it('캐시된 사진을 다시 열어도 표시 중인 주소를 유지한다', async () => {
  const revoked = new Set<string>()
  let serial = 0
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => `blob:photo-${++serial}`),
      revokeObjectURL: vi.fn((url: string) => revoked.add(url)),
    }),
  )
  const client = new QueryClient({ defaultOptions: { queries: { staleTime: Infinity } } })
  client.setQueryData(['applicant-photo', 'recruitment', 'applicant'], {
    blob: new Blob(['photo']),
    example: false,
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(new Blob(['photo']), { status: 200 }))),
  )
  const { container } = render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <ApplicantAvatar recruitmentId="recruitment" applicationId="applicant" />
      </QueryClientProvider>
    </StrictMode>,
  )
  await waitFor(() => {
    const src = container.querySelector('img')?.getAttribute('src')
    expect(src).toMatch(/^blob:photo-/)
    expect(revoked.has(src!)).toBe(false)
  })
})
