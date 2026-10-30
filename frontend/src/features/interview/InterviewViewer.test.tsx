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

it('미지정 질문의 담당 변경을 전달한다', () => {
  state.questions = [
    {
      questionId: 'q1',
      text: '경험 질문',
      source: 'AI',
      answer: '',
      reason: null,
      interviewerRole: null,
    },
  ]
  const { unmount } = render(
    <InterviewViewer
      stageId="stage"
      recruitmentId="recruit"
      detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
      editable
    />,
  )
  const select = screen.getByRole('combobox', { name: '경험 질문 담당' })
  expect(select).toHaveValue('')
  // 🎤 담당이 비어 있으면 고를 수 없는 안내 칸만 보이고, '미지정' 선택지는 없다
  expect(screen.getByRole('option', { name: '담당 선택' })).toBeDisabled()
  expect(screen.queryByRole('option', { name: '미지정' })).not.toBeInTheDocument()
  fireEvent.change(select, { target: { value: 'HR' } })
  expect(state.assign).toHaveBeenCalledWith(
    { questionId: 'q1', interviewerRole: 'HR' },
    expect.any(Object),
  )
  unmount()
  state.questions = []
})

it('담당이 정해진 질문은 인사 · 실무만 고를 수 있다', () => {
  // 🎤 면접관 2명 고정: 정해진 담당을 비우는 선택지(미지정 · 담당 선택)가 없다
  state.questions = [
    {
      questionId: 'q2',
      text: '지원 동기 질문',
      source: 'AI',
      answer: '',
      reason: null,
      interviewerRole: 'HR',
    },
  ]
  const { unmount } = render(
    <InterviewViewer
      stageId="stage"
      recruitmentId="recruit"
      detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
      editable
    />,
  )
  const select = screen.getByRole('combobox', { name: '지원 동기 질문 담당' })
  expect(select).toHaveValue('HR')
  const options = Array.from((select as HTMLSelectElement).options).map((option) => option.text)
  expect(options).toEqual(['인사', '실무'])
  unmount()
  state.questions = []
})
