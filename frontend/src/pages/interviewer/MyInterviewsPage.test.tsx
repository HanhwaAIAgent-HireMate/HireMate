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
  it('배정된 면접을 채용 · 전형별로 묶어 면접 시간순으로 보여 준다', async () => {
    renderPage([
      item('a2', '박서준', '2026-11-03T05:00:00Z', 'SCHEDULED'),
      item('a1', '김하늘', '2026-11-03T02:00:00Z', 'IN_PROGRESS'),
    ])

    const group = await screen.findByRole('region', {
      name: '결제 플랫폼 백엔드 개발자 1차 기술 면접',
    })
    const links = group.querySelectorAll('a')
    expect(links[0]).toHaveTextContent('김하늘')
    expect(links[0]).toHaveTextContent('진행 중')
    expect(links[0]).toHaveAttribute('href', '/interviewer/stages/s1?candidate=a1')
    expect(links[1]).toHaveTextContent('박서준')
  })

  it('배정된 면접이 없으면 안내를 보여 준다', async () => {
    renderPage([])

    expect(await screen.findByText(/아직 배정된 면접이 없어요/)).toBeInTheDocument()
  })
})
