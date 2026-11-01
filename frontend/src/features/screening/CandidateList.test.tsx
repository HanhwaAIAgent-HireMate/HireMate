import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { StageOverview } from '@/features/screening/api'
import { CandidateList } from '@/features/screening/CandidateList'

const state = vi.hoisted(() => ({
  live: vi.fn(),
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
vi.mock('@/features/interview/opinions', () => ({
  useStageOpinions: () => ({ data: [] }),
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
  it('배정된 면접의 예정, 진행 중, 끝남을 지원자마다 구분하고 실시간으로 구독한다', () => {
    renderList()
    expect(within(screen.getByTestId('a1')).getByLabelText('면접 상태: 예정')).toBeVisible()
    expect(within(screen.getByTestId('a2')).getByLabelText('면접 상태: 진행 중')).toBeVisible()
    expect(within(screen.getByTestId('a3')).getByLabelText('면접 상태: 끝남')).toBeVisible()
    expect(within(screen.getByTestId('a4')).queryByLabelText(/면접 상태/)).not.toBeInTheDocument()
    expect(state.live).toHaveBeenCalledWith('s1', true)
  })

  it('면접 전형이 아니면 면접 상태를 표시하거나 실시간 구독하지 않는다', () => {
    renderList('DOCUMENT')
    expect(screen.queryByLabelText(/면접 상태/)).not.toBeInTheDocument()
    expect(state.live).toHaveBeenCalledWith('s1', false)
  })
})
