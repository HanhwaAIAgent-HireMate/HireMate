import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { MyInterviewsPage } from '@/pages/interviewer/MyInterviewsPage'

const stages = [
  {
    stageId: 's1',
    stageName: '1차 기술 면접',
    status: 'ACTIVE',
    recruitmentId: 'r1',
    recruitmentTitle: '결제 플랫폼 백엔드 개발자',
    roles: ['PRACTICAL'],
    candidateCount: 8,
  },
  {
    stageId: 's2',
    stageName: '1차 면접',
    status: 'CONFIRMED',
    recruitmentId: 'r2',
    recruitmentTitle: '데이터 엔지니어',
    roles: ['HR'],
    candidateCount: 3,
  },
]

function renderPage(body: unknown) {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json(body))),
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
  it('지정된 면접 전형을 채용 · 전형 · 내 담당 · 지원자 수와 함께 보여 준다', async () => {
    renderPage(stages)

    const active = await screen.findByRole('article', {
      name: '결제 플랫폼 백엔드 개발자 1차 기술 면접',
    })
    expect(active).toHaveTextContent('실무')
    expect(active).toHaveTextContent('지원자 8명')
    expect(active).toHaveTextContent('진행 중')
    expect(screen.getByRole('article', { name: '데이터 엔지니어 1차 면접' })).toHaveTextContent(
      '결과 확정 · 읽기만',
    )
  })

  it('지정된 면접이 없으면 안내를 보여 준다', async () => {
    renderPage([])

    expect(await screen.findByText(/아직 지정된 면접이 없어요/)).toBeInTheDocument()
  })
})
