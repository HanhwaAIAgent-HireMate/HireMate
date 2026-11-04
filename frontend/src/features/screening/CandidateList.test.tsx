import { render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { StageOverview } from '@/features/screening/api'
import { CandidateList } from '@/features/screening/CandidateList'

const state = vi.hoisted(() => ({
  live: vi.fn(),
  // 서류 전형: 선 위 지원자와 블라인드 위반 의심 지원자 (서버가 의심 지원자를 맨 아래로 보낸다)
  above: [] as string[],
  suspects: [] as string[],
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
  // a1 · a2는 같은 시간 면접(a2 불참), a3은 그 전 시간에 끝났고, a4는 일정이 없다
  progress: [
    { applicationId: 'a1', status: 'IN_PROGRESS' },
    { applicationId: 'a2', status: 'ABSENT' },
    { applicationId: 'a3', status: 'ENDED' },
  ],
  schedules: [
    { applicationId: 'a1', scheduledAt: '2026-11-03T05:00:00Z' },
    { applicationId: 'a2', scheduledAt: '2026-11-03T05:00:00Z' },
    { applicationId: 'a3', scheduledAt: '2026-11-02T03:00:00Z' },
  ],
}))

vi.mock('@/features/interview/live', () => ({
  useInterviewStageLive: (stageId: string, enabled: boolean) => {
    state.live(stageId, enabled)
    return { connected: true }
  },
  useStageInterviewProgress: () => ({ data: state.progress }),
}))
vi.mock('@/features/interview/api', () => ({
  useStageSchedules: () => ({ data: state.schedules }),
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
            aboveLine: state.above.includes(applicationId),
          })),
          total: 4,
          schoolSuspects: state.suspects,
        },
      ],
    },
    isPending: false,
    hasNextPage: false,
    isFetchingNextPage: false,
    fetchNextPage: vi.fn(),
  }),
  useSelectionActions: () => ({}),
  NO_FILTER: { decisions: [], criteria: [], talents: [] },
  isFiltered: () => false,
}))
vi.mock('@/features/screening/table', () => ({
  GROUP_LABELS: {},
  useCandidateTable: () => ({ data: { features: [] }, isPending: false }),
}))
vi.mock('@/features/screening/CandidateTile', () => ({
  CandidateTile: ({
    row,
    note,
    suspect,
  }: {
    row: { applicationId: string }
    note: ReactNode
    suspect?: boolean
  }) => (
    <div data-testid={row.applicationId} data-suspect={suspect}>
      {note}
    </div>
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
  state.above = []
  state.suspects = []
  vi.unstubAllGlobals()
})

describe('면접 전형 지원자 목록', () => {
  it('면접 시간별로 나눠 시간 순으로 두고, 칸마다 그 시간 면접의 상태를 한 번 보여 준다', () => {
    renderList()
    const headings = screen.getAllByRole('heading', { level: 3 })
    expect(headings).toHaveLength(3)
    expect(headings[0]).toHaveTextContent('1명')
    expect(headings[0]).toHaveTextContent('면접 종료')
    expect(headings[1]).toHaveTextContent('2명')
    expect(headings[1]).toHaveTextContent('면접 진행 중')
    // 일정이 없는 지원자는 맨 아래 '일정 미정' 칸에 모아 정할 일이 남았음을 보인다
    expect(headings[2]).toHaveTextContent('일정 미정 · 1명')
    expect(headings[2]).toHaveTextContent('면접 일정을 정해 주세요')
    expect(screen.getAllByTestId(/^a\d$/).map((tile) => tile.dataset.testid)).toEqual([
      'a3',
      'a1',
      'a2',
      'a4',
    ])
    // 카드에는 그 시간에서 빠진 불참만 붙인다
    expect(within(screen.getByTestId('a2')).getByLabelText('면접 상태: 불참')).toBeVisible()
    expect(within(screen.getByTestId('a1')).queryByLabelText(/면접 상태/)).not.toBeInTheDocument()
    expect(state.live).toHaveBeenCalledWith('s1', true)
  })

  it('면접관 의견 배지는 면접이 종료된 지원자에게만 보이고 내지 않은 의견은 미제출로 보인다', () => {
    renderList()
    // 진행 중(a1)과 불참(a2)에는 의견 배지가 없다
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
    expect(screen.queryAllByRole('heading', { level: 3 })).toHaveLength(0)
    expect(state.live).toHaveBeenCalledWith('s1', false)
  })
})

describe('서류 전형 블라인드 위반 의심', () => {
  it('위반 의심 지원자는 맨 아래 노란 칸에 모으고 필수 조건 미충족 수에서 뺀다', () => {
    state.above = ['a1']
    state.suspects = ['a4']
    renderList('DOCUMENT')
    expect(screen.getByText(/필수 조건 미충족 2명/)).toBeInTheDocument()
    expect(screen.getByText(/블라인드 위반 의심 1명/)).toBeInTheDocument()
    expect(screen.getByTestId('a4').dataset.suspect).toBe('true')
    expect(screen.getByTestId('a2').dataset.suspect).toBe('false')
  })

  it('위반 의심 지원자가 없으면 노란 칸을 보이지 않는다', () => {
    state.above = ['a1', 'a2', 'a3', 'a4']
    renderList('DOCUMENT')
    expect(screen.queryByText(/블라인드 위반 의심/)).not.toBeInTheDocument()
  })
})
