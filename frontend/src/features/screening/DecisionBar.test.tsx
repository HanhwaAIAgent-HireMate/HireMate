import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DecisionBar } from '@/features/screening/DecisionBar'

const decide = vi.hoisted(() => vi.fn())

vi.mock('@/features/screening/api', () => ({
  useCandidateDetail: () => ({ data: undefined }),
  useDecisionActions: () => ({
    decide: { mutate: decide, isPending: false },
    revert: { mutate: vi.fn(), isPending: false },
  }),
  useStageOverview: () => ({ data: { type: 'INTERVIEW' } }),
}))
vi.mock('@/features/screening/store', () => ({
  useStageUi: () => ({ checked: ['a1'], setChecked: vi.fn(), openId: null }),
}))
vi.mock('@/features/interview/opinions', async (original) => ({
  ...(await original<typeof import('@/features/interview/opinions')>()),
  useStageOpinions: () => ({
    data: [
      {
        applicationId: 'a1',
        opinions: [
          { role: 'HR', submitted: true, unassigned: false },
          { role: 'PRACTICAL', submitted: false, unassigned: false },
        ],
      },
    ],
  }),
}))

describe('DecisionBar 면접관 의견 확인', () => {
  it('의견이 빠진 지원자를 결정하면 확인 창을 띄우고, 그래도 결정하면 결정한다', () => {
    render(<DecisionBar stageId="s1" tabId="t1" editable names={{ a1: '김하늘' }} />)

    fireEvent.click(screen.getByRole('button', { name: '합격' }))
    expect(decide).not.toHaveBeenCalled()
    expect(screen.getByText('김하늘: 실무 의견이 아직 없어요')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '그래도 합격' }))
    expect(decide).toHaveBeenCalledWith({ ids: ['a1'], decision: 'PASS' }, expect.anything())
  })
})

describe('DecisionBar 결정 알림', () => {
  it('결정 알림은 2초 뒤 흐려지며 사라진다', () => {
    vi.useFakeTimers()
    decide.mockImplementation((_variables, options: { onSuccess: () => void }) =>
      options.onSuccess(),
    )
    render(<DecisionBar stageId="s1" tabId="t1" editable names={{ a1: '김하늘' }} />)

    fireEvent.click(screen.getByRole('button', { name: '불합격' }))
    fireEvent.click(screen.getByRole('button', { name: '그래도 불합격' }))
    expect(screen.getByRole('status')).toHaveTextContent('김하늘 님을 불합격 처리했어요')

    act(() => {
      vi.advanceTimersByTime(1700)
    })
    expect(screen.getByRole('status')).toHaveClass('opacity-0')
    act(() => {
      vi.advanceTimersByTime(300)
    })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
    vi.useRealTimers()
  })
})
