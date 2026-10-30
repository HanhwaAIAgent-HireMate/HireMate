import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { InterviewViewer } from './InterviewViewer'
import type { CandidateDetail } from '@/features/screening/api'

const state = vi.hoisted(() => ({
  questions: [] as {
    questionId: string
    text: string
    source: string
    answer: string
    reason: null
    interviewerRole: 'HR' | 'PRACTICAL' | null
  }[],
  assign: vi.fn(),
}))

vi.mock('@/features/interview/api', () => ({
  useInterview: () => ({ data: { questions: state.questions, previous: [], schedule: null } }),
  useInterviewPreparing: () => ({ isPending: true, data: undefined }),
  useInterviewActions: () => ({
    regenerate: { isPending: false },
    assignRole: { isPending: false, mutate: state.assign },
  }),
}))

describe('면접 질문 로딩', () => {
  it('첫 지원자의 생성 상태를 확인하는 동안 로딩을 표시한다', () => {
    render(
      <InterviewViewer
        stageId="stage"
        recruitmentId="recruit"
        detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
        editable
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('질문 생성 중이에요')
    expect(screen.queryByText(/아직 질문이 없어요/)).not.toBeInTheDocument()
  })
})

// 🎤 10/30: 담당은 색깔 태그. 누를 때마다 인사 ↔ 실무로 바뀐다
function renderWith(interviewerRole: 'HR' | 'PRACTICAL' | null, editable = true) {
  state.assign.mockClear()
  state.questions = [
    {
      questionId: 'q1',
      text: '경험 질문',
      source: 'AI',
      answer: '',
      reason: null,
      interviewerRole,
    },
  ]
  return render(
    <InterviewViewer
      stageId="stage"
      recruitmentId="recruit"
      detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
      editable={editable}
    />,
  )
}

it('인사 태그를 누르면 실무로 바꾼다', () => {
  const { unmount } = renderWith('HR')
  const tag = screen.getByRole('button', { name: /경험 질문 담당: 인사/ })
  expect(tag).toHaveAttribute('title', '클릭하면 실무로 바꿔요')
  fireEvent.click(tag)
  expect(state.assign).toHaveBeenCalledWith(
    { questionId: 'q1', interviewerRole: 'PRACTICAL' },
    expect.any(Object),
  )
  unmount()
})

it('실무 태그를 다시 누르면 인사로 바꾼다', () => {
  const { unmount } = renderWith('PRACTICAL')
  fireEvent.click(screen.getByRole('button', { name: /경험 질문 담당: 실무/ }))
  expect(state.assign).toHaveBeenCalledWith(
    { questionId: 'q1', interviewerRole: 'HR' },
    expect.any(Object),
  )
  unmount()
})

it('담당이 비어 있던 옛 질문은 담당 선택 태그로 보이고, 누르면 인사부터 정한다', () => {
  const { unmount } = renderWith(null)
  fireEvent.click(screen.getByRole('button', { name: /경험 질문 담당: 담당 선택/ }))
  expect(state.assign).toHaveBeenCalledWith(
    { questionId: 'q1', interviewerRole: 'HR' },
    expect.any(Object),
  )
  unmount()
})

it('확정된 전형에서는 담당 태그를 누를 수 없다', () => {
  const { unmount } = renderWith('HR', false)
  expect(screen.queryByRole('button', { name: /경험 질문 담당/ })).not.toBeInTheDocument()
  expect(screen.getByLabelText('경험 질문 담당: 인사')).toBeInTheDocument()
  unmount()
  state.questions = []
})
