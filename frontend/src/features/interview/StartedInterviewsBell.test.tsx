import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { StartedInterviewsBell } from '@/features/interview/StartedInterviewsBell'

const started = (applicationId: string, applicantName: string, startedAt: string) => ({
  stageId: 's1',
  applicationId,
  recruitmentId: 'r1',
  recruitmentTitle: '결제 플랫폼 백엔드 개발자',
  stageName: '1차 기술 면접',
  applicantName,
  startedAt,
})

function renderBell(items: unknown[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json(items))),
  )
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <StartedInterviewsBell memberId="m1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('HR 알림: 시작한 면접', () => {
  it('새로 시작한 면접을 종에 세고, 열면 면접 전형으로 가는 알림을 보여 주고, 닫으면 읽은 것으로 둔다', async () => {
    renderBell([
      started('a2', '박서준', '2026-11-02T05:00:00Z'),
      started('a1', '김하늘', '2026-11-02T02:00:00Z'),
    ])
    fireEvent.click(await screen.findByRole('button', { name: '알림 2개' }))

    const link = screen.getByRole('link', { name: /박서준 면접이 시작됐어요/ })
    expect(link).toHaveAttribute('href', '/hr/recruitments/r1/stages/s1')
    expect(link).toHaveTextContent('결제 플랫폼 백엔드 개발자 · 1차 기술 면접')
    expect(screen.getByRole('link', { name: /김하늘 면접이 시작됐어요/ })).toBeInTheDocument()

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
    expect(await screen.findByRole('button', { name: '알림' })).toBeInTheDocument()
    expect(localStorage.getItem('hiremate:interview-started-seen:m1')).toBe(
      String(Date.parse('2026-11-02T05:00:00Z')),
    )
  })

  it('마지막으로 열어 본 뒤에 시작한 면접만 새 알림으로 센다', async () => {
    localStorage.setItem(
      'hiremate:interview-started-seen:m1',
      String(Date.parse('2026-11-02T03:00:00Z')),
    )
    renderBell([
      started('a2', '박서준', '2026-11-02T05:00:00Z'),
      started('a1', '김하늘', '2026-11-02T02:00:00Z'),
    ])

    expect(await screen.findByRole('button', { name: '알림 1개' })).toBeInTheDocument()
  })

  it('시작한 면접이 없으면 새 알림이 없다고 알린다', async () => {
    renderBell([])
    fireEvent.click(await screen.findByRole('button', { name: '알림' }))

    expect(await screen.findByText('새 알림이 없어요.')).toBeInTheDocument()
  })
})
