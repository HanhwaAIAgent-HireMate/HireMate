import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { MyInterviewsPage } from '@/pages/interviewer/MyInterviewsPage'

const item = (
  applicationId: string,
  applicantName: string,
  scheduledAt: string | null,
  status: string,
) => ({
  stageId: 's1',
  applicationId,
  recruitmentId: 'r1',
  recruitmentTitle: '결제 플랫폼 백엔드 개발자',
  stageName: '1차 기술 면접',
  applicantName,
  schedule: scheduledAt ? { scheduledAt, interviewers: '' } : null,
  myRole: 'PRACTICAL',
  status,
})

function renderPage(items: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json({ items, total: items.length, page: 0, size: 50 }))),
  )
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <MyInterviewsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('MyInterviewsPage', () => {
  it('배정된 면접 전형 하나를 카드 하나로 보여 주고 지원자는 따로 나열하지 않는다', async () => {
    renderPage([
      item('a2', '박서준', '2026-11-03T05:00:00Z', 'SCHEDULED'),
      item('a1', '김하늘', '2026-11-03T02:00:00Z', 'IN_PROGRESS'),
      item('a3', '이도윤', '2026-11-02T05:00:00Z', 'ENDED'),
    ])

    const card = await screen.findByRole('link', { name: /1차 기술 면접/ })
    expect(screen.getAllByRole('link')).toHaveLength(1)
    expect(card).toHaveAttribute('href', '/interviewer/stages/s1')
    expect(card).toHaveTextContent('결제 플랫폼 백엔드 개발자')
    expect(card).toHaveTextContent('지원자 3명')
    expect(card).toHaveTextContent('진행 중 1')
    expect(card).toHaveTextContent('예정 1')
    expect(card).toHaveTextContent('종료 1')
    expect(card).toHaveTextContent(/다음 면접 \d/)
    expect(screen.getByLabelText('1차 기술 면접 내 담당: 실무')).toBeInTheDocument()
    expect(card).not.toHaveTextContent('김하늘')
    expect(card).not.toHaveTextContent('박서준')
  })

  it('전형마다 카드를 따로 둔다', async () => {
    renderPage([
      item('a1', '김하늘', null, 'SCHEDULED'),
      { ...item('a2', '박서준', null, 'SCHEDULED'), stageId: 's2', stageName: '2차 임원 면접' },
    ])

    expect(await screen.findByRole('link', { name: /1차 기술 면접/ })).toHaveAttribute(
      'href',
      '/interviewer/stages/s1',
    )
    expect(screen.getByRole('link', { name: /2차 임원 면접/ })).toHaveAttribute(
      'href',
      '/interviewer/stages/s2',
    )
  })

  it('배정된 면접이 없으면 안내를 보여 준다', async () => {
    renderPage([])

    expect(await screen.findByText(/아직 배정된 면접이 없어요/)).toBeInTheDocument()
  })
})
