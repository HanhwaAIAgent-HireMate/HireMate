import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { StrictMode } from 'react'

import { ApplicantAvatar } from '@/components/ApplicantAvatar'

afterEach(() => vi.unstubAllGlobals())

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
      <ApplicantAvatar recruitmentId="recruitment" applicationId="applicant" name="지원자" />
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
  client.setQueryData(['applicant-photo', 'recruitment', 'applicant'], new Blob(['photo']))
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(new Blob(['photo']), { status: 200 }))),
  )
  const { container } = render(
    <StrictMode>
      <QueryClientProvider client={client}>
        <ApplicantAvatar recruitmentId="recruitment" applicationId="applicant" name="지원자" />
      </QueryClientProvider>
    </StrictMode>,
  )
  await waitFor(() => {
    const src = container.querySelector('img')?.getAttribute('src')
    expect(src).toMatch(/^blob:photo-/)
    expect(revoked.has(src!)).toBe(false)
  })
})
