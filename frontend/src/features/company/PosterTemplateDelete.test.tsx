import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { PosterTemplateDelete } from './PosterTemplateDelete'
import { posterBrandKey } from '@/features/posting/poster-api'
import { resetCsrf } from '@/lib/api/client'

const fetchMock = vi.fn<typeof fetch>()
beforeEach(() => {
  resetCsrf()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function setup(onDeleted = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <PosterTemplateDelete id="custom-id" name="금융 채용형" onDeleted={onDeleted} />
    </QueryClientProvider>,
  )
  return client
}

it('항상 보이는 삭제 버튼은 확인 창만 열고 취소하면 삭제하지 않는다', () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: '금융 채용형 템플릿 삭제' }))
  expect(screen.getByRole('dialog')).toHaveTextContent('설정에 저장한 기본 템플릿으로 돌아가요')
  expect(fetchMock).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '취소' }))
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it('삭제를 확인한 후에만 회사 템플릿 목록을 갱신하며 공고 캐시는 유지한다', async () => {
  const brand = { template: 'CLASSIC', color: '#082858', templates: [] }
  fetchMock.mockResolvedValueOnce(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
  fetchMock.mockResolvedValueOnce(Response.json(brand))
  const onDeleted = vi.fn()
  const client = setup(onDeleted)
  client.setQueryData(['posting', 'draft'], { poster: { color: '#082858' } })
  fireEvent.click(screen.getByRole('button', { name: '금융 채용형 템플릿 삭제' }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  const request = fetchMock.mock.calls[1]?.[0] as Request
  expect(request.method).toBe('DELETE')
  expect(request.url).toContain('/poster-brand/templates/custom-id')
  expect(client.getQueryData(posterBrandKey)).toEqual(brand)
  expect(onDeleted).toHaveBeenCalledExactlyOnceWith(brand)
  expect(client.getQueryData(['posting', 'draft'])).toEqual({ poster: { color: '#082858' } })
})

it('삭제 요청이 실패하면 선택한 디자인을 바꾸지 않는다', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
  fetchMock.mockResolvedValueOnce(Response.json({ message: '실패' }, { status: 500 }))
  const onDeleted = vi.fn()
  setup(onDeleted)
  fireEvent.click(screen.getByRole('button', { name: '금융 채용형 템플릿 삭제' }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '삭제' })).toBeEnabled())
  expect(onDeleted).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog')).toBeInTheDocument()
})
