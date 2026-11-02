import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { StageOverview } from '@/features/screening/api'
import { CandidateList } from '@/features/screening/CandidateList'

const state = vi.hoisted(() => ({
  live: vi.fn(),
  // 인사는 a3에만 추천을 냈고 실무는 아무도 내지 않았다
  opinions: (['a1', 'a2', 'a3'] as const).map((applicationId) => ({
    applicationId,
    opinions: [
      {
        memberId: 'hr',
        role: 'HR',
        recommendation: applicationId === 'a3' ? 'RECOMMEND' : null,
        unassigned: false,
      },
      { memberId: 'practical', role: 'PRACTICAL', recommendation: null, unassigned: false },
    ],
  })),
  progress: [
    { applicationId: 'a1', status: 'SCHEDULED' },
    { applicationId: 'a2', status: 'IN_PROGRESS' },
    { applicationId: 'a3', status: 'ENDED' },
  ],
}))

vi.mock('@/features/interview/live', () => ({
  useInterviewStageLive: (stageId: string, enabled: boolean) => {
    state.live(stageId, enabled)
    return { connected: true }
  },
  useStageInterviewProgress: () => ({ data: state.progress }),
}))
vi.mock('@/features/interview/opinions', async (original) => ({
  ...(await original<typeof import('@/features/interview/opinions')>()),
  useStageOpinions: () => ({ data: state.opinions }),
}))
vi.mock('@/features/screening/api', () => ({
  useCandidates: () => ({
    data: {
      pages: [
        {
          items: ['a1', 'a2', 'a3', 'a4'].map((applicationId) => ({
            applicationId,
            name: applicationId,
            decision: 'PENDING',
          })),
          total: 4,
        },
      ],
    },
    isPending: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  useSelectionActions: () => ({}),
  useRequirements: () => ({ data: [], isPending: false }),
  useUpdateRequirements: () => ({ mutate: vi.fn(), isPending: false }),
}))
vi.mock('@/features/screening/table', () => ({
  GROUP_LABELS: {},
  useCandidateTable: () => ({ data: { features: [] }, isPending: false }),
}))
vi.mock('@/features/screening/CandidateTile', () => ({
  CandidateTile: ({ row, note }: { row: { applicationId: string }; note: ReactNode }) => (
    <div data-testid={row.applicationId}>{note}</div>
  ),
}))
vi.mock('@/features/screening/CandidateItem', () => ({
  RowButton: () => null,
}))

function renderList(type: StageOverview['type'] = 'INTERVIEW') {
  vi.stubGlobal(
    'IntersectionObserver',
    class {
      observe() {}
      disconnect() {}
    },
  )
  return render(
    <CandidateList
      overview={{ stageId: 's1', type, counts: { total: 4 } } as StageOverview}
      tabId={null}
      editable={false}
    />,
  )
}

afterEach(() => {
  state.live.mockClear()
  vi.unstubAllGlobals()
})

describe('면접 전형 지원자 목록', () => {
  it('배정된 면접의 예정, 진행 중, 종료를 지원자마다 구분하고 실시간으로 구독한다', () => {
    renderList()
    expect(within(screen.getByTestId('a1')).getByLabelText('면접 상태: 예정')).toBeVisible()
    expect(within(screen.getByTestId('a2')).getByLabelText('면접 상태: 진행 중')).toBeVisible()
    const ended = within(screen.getByTestId('a3')).getByLabelText('면접 상태: 종료')
    expect(ended).toBeVisible()
    expect(ended).toHaveTextContent('면접 종료')
    // 종료는 예정(회색)과 다른 색으로 구분한다
    expect(ended).toHaveClass('bg-sky-100')
    expect(within(screen.getByTestId('a1')).getByLabelText('면접 상태: 예정')).toHaveClass(
      'bg-muted',
    )
    expect(within(screen.getByTestId('a4')).queryByLabelText(/면접 상태/)).not.toBeInTheDocument()
    expect(state.live).toHaveBeenCalledWith('s1', true)
  })

  it('면접관 의견 배지는 면접이 종료된 지원자에게만 보이고 내지 않은 의견은 미제출로 보인다', () => {
    renderList()
    expect(within(screen.getByTestId('a1')).queryByLabelText('면접관 의견')).not.toBeInTheDocument()
    expect(within(screen.getByTestId('a2')).queryByLabelText('면접관 의견')).not.toBeInTheDocument()
    const ended = within(screen.getByTestId('a3')).getByLabelText('면접관 의견')
    expect(ended).toHaveTextContent('인사 추천')
    expect(ended).toHaveTextContent('실무 미제출')
    expect(ended).not.toHaveTextContent('아직')
  })

  it('면접 전형이 아니면 면접 상태를 표시하거나 실시간 구독하지 않는다', () => {
    renderList('DOCUMENT')
    expect(screen.queryByLabelText(/면접 상태/)).not.toBeInTheDocument()
    expect(state.live).toHaveBeenCalledWith('s1', false)
  })
})
