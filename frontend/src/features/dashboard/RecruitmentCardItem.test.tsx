import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import type { RecruitmentCard } from './api'
import { RecruitmentCardItem } from './RecruitmentCardItem'
import { resetCsrf } from '@/lib/api/client'

const card: RecruitmentCard = {
  recruitmentId: 'draft-id',
  postingId: 'posting-id',
  title: 'AX 개발자',
  status: 'DRAFT',
  applicantCount: 0,
  closeAt: null,
  currentStageId: null,
  steps: [],
  createdAt: '2026-11-03T00:00:00Z',
}
const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => {
  resetCsrf()
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function setup(status: RecruitmentCard['status'] = 'DRAFT') {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RecruitmentCardItem card={{ ...card, status }} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return client
}

it('휴지통은 이동이나 삭제 대신 확인 창을 열고 취소하면 요청하지 않는다', () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'AX 개발자 작성 중 공고 삭제' }))
  expect(screen.getByRole('alertdialog')).toHaveTextContent('AX 개발자')
  expect(screen.getByRole('alertdialog')).toHaveTextContent('복구할 수 없어요')
  expect(fetchMock).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: '취소' }))
  expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  expect(fetchMock).not.toHaveBeenCalled()
})

it.each(['PUBLISHED', 'IN_PROGRESS'] as const)('%s 공고에는 삭제 버튼이 없다', (status) => {
  setup(status)
  expect(screen.queryByRole('button', { name: /공고 삭제/ })).not.toBeInTheDocument()
})

it('종료된 공고도 삭제할 수 있고 확인 창에서 기록 보관을 안내한다', () => {
  setup('CLOSED')
  fireEvent.click(screen.getByRole('button', { name: 'AX 개발자 종료된 공고 삭제' }))
  expect(screen.getByRole('alertdialog')).toHaveTextContent('지원자와 평가 기록은 보관')
  expect(fetchMock).not.toHaveBeenCalled()
})

it('확인한 뒤에만 삭제하고 목록과 공고 캐시를 갱신한다', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
  fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))
  const client = setup()
  client.setQueryData(['recruitments', 'ALL', ''], { items: [card] })
  client.setQueryData(['posting', card.recruitmentId], { title: card.title })
  fireEvent.click(screen.getByRole('button', { name: /공고 삭제/ }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument())
  const request = fetchMock.mock.calls[1]?.[0] as Request
  expect(request.method).toBe('DELETE')
  expect(request.url).toContain('/api/recruitments/draft-id/posting')
  expect(client.getQueryState(['recruitments', 'ALL', ''])?.isInvalidated).toBe(true)
  expect(client.getQueryData(['posting', card.recruitmentId])).toBeUndefined()
})

it('삭제가 실패하면 창을 유지하고 재시도할 수 있다', async () => {
  fetchMock.mockResolvedValueOnce(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
  fetchMock.mockResolvedValueOnce(Response.json({ code: 'RECRUITMENT_LOCKED' }, { status: 409 }))
  setup()
  fireEvent.click(screen.getByRole('button', { name: /공고 삭제/ }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('공고 게시 중이거나 전형 진행 중')
  expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: '취소' })).toBeEnabled()
})
