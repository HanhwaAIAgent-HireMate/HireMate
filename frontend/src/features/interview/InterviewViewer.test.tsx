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
    parentQuestionId?: string | null
  }[],
  assign: vi.fn(),
  add: vi.fn(),
  previous: [] as unknown[],
}))

// 면접관 배정은 따로 검사한다 (InterviewAssign.test.tsx)
vi.mock('@/features/interview/InterviewAssign', () => ({ InterviewAssign: () => null }))
vi.mock('@/features/interview/HrOpinions', () => ({ HrOpinions: () => null }))

vi.mock('@/features/interview/api', () => ({
  useInterview: () => ({
    data: { questions: state.questions, previous: state.previous, schedule: null },
  }),
  useInterviewPreparing: () => ({ isPending: true, data: undefined }),
  useInterviewActions: () => ({
    regenerate: { isPending: false },
    assignRole: { isPending: false, mutate: state.assign },
    add: { isPending: false, mutate: state.add },
    answer: { mutateAsync: vi.fn() },
    suggestFollowUps: { mutateAsync: vi.fn() },
    addFollowUp: { isPending: false, mutate: vi.fn() },
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

it('직접 추가할 질문의 담당을 선택해 함께 저장한다', () => {
  state.add.mockClear()
  const { unmount } = renderWith('HR')
  fireEvent.click(screen.getByRole('button', { name: '질문 추가' }))
  fireEvent.change(screen.getByLabelText('추가할 질문'), { target: { value: '직접 물어볼 질문' } })
  fireEvent.click(screen.getByRole('button', { name: /추가할 질문 담당: 인사/ }))
  fireEvent.click(screen.getByRole('button', { name: '추가' }))
  expect(state.add).toHaveBeenCalledWith(
    { text: '직접 물어볼 질문', interviewerRole: 'PRACTICAL' },
    expect.any(Object),
  )
  unmount()
})

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

// 🎤 꼬리질문은 원래 질문 아래에 들여 쓰고, 2단계 질문과 이미 꼬리질문이 딸린 질문에는 받기 버튼이 없다
it('꼬리질문은 2단계까지만 받기 버튼을 보여 준다', () => {
  const question = (questionId: string, parentQuestionId: string | null) => ({
    questionId,
    text: `${questionId} 질문`,
    source: 'AI',
    answer: `${questionId} 답변`,
    reason: null,
    interviewerRole: 'PRACTICAL' as const,
    parentQuestionId,
  })
  state.questions = [
    question('q1', null),
    question('f1', 'q1'),
    question('f2', 'f1'),
    question('q2', null),
  ]
  const { unmount } = render(
    <InterviewViewer
      stageId="stage"
      recruitmentId="recruit"
      detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
      editable
    />,
  )
  // q1 · f1은 이미 꼬리질문이 있고, f2는 2단계라 버튼이 없다. q2만 받을 수 있다
  expect(screen.getAllByRole('button', { name: '꼬리질문 받기' })).toHaveLength(1)
  unmount()
  state.questions = []
})

// 🎤 꼬리질문 접기: 기본은 펼침, 접으면 카드는 숨기고 첫 줄과 답 유무만 보여 준다. 새 꼬리질문이 생기면 다시 펼친다
it('꼬리질문은 기본으로 펼쳐 두고 접기 버튼으로 숨긴다', () => {
  // 새로 생긴 질문으로 스크롤하는데, 테스트용 브라우저(jsdom)에는 scrollIntoView가 없다
  Element.prototype.scrollIntoView = vi.fn()
  const question = (questionId: string, parentQuestionId: string | null, answer: string) => ({
    questionId,
    text: `${questionId} 질문`,
    source: 'AI',
    answer,
    reason: null,
    interviewerRole: 'PRACTICAL' as const,
    parentQuestionId,
  })
  state.questions = [
    question('q1', null, '답'),
    question('f1', 'q1', '꼬리 답'),
    question('f2', 'f1', ''),
  ]
  const view = () => (
    <InterviewViewer
      stageId="stage"
      recruitmentId="recruit"
      detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
      editable
    />
  )
  const { rerender, unmount } = render(view())
  const toggle = screen.getByRole('button', { name: /꼬리질문 2개 접기/ })
  expect(toggle).toHaveAttribute('aria-expanded', 'true')
  expect(toggle).toHaveTextContent('답변 1/2')
  expect(screen.getByLabelText('f1 질문 답변')).toBeVisible()

  fireEvent.click(toggle)
  expect(screen.getByRole('button', { name: /꼬리질문 2개 펼치기/ })).toHaveAttribute(
    'aria-expanded',
    'false',
  )
  // 카드는 숨기기만 한다 (적던 답이 남도록 화면에서 빼지 않는다)
  expect(screen.getByLabelText('f1 질문 답변').closest('.hidden')).not.toBeNull()
  // 접힌 요약 줄에 꼬리질문 첫 줄이 보인다 (숨긴 카드에도 같은 글이 있어 2곳)
  expect(screen.getAllByText('f2 질문')).toHaveLength(2)
  expect(screen.getByText('· 답변 없음')).toBeInTheDocument()

  // 꼬리질문이 새로 생기면 자동으로 펼친다
  state.questions = [...state.questions, question('q2', null, ''), question('g1', 'q2', '')]
  rerender(view())
  expect(screen.getByRole('button', { name: /꼬리질문 2개 펼치기/ })).toBeInTheDocument()
  state.questions = [
    ...state.questions.slice(0, 3),
    question('f3', 'q1', ''),
    ...state.questions.slice(3),
  ]
  rerender(view())
  expect(screen.getByRole('button', { name: /꼬리질문 3개 접기/ })).toBeInTheDocument()
  unmount()
  state.questions = []
})

it('지난 면접 기록의 꼬리질문은 기본으로 접어 두고 펼칠 수 있다', () => {
  const question = (questionId: string, parentQuestionId: string | null) => ({
    questionId,
    text: `${questionId} 지난 질문`,
    source: 'AI',
    answer: `${questionId} 지난 답`,
    reason: null,
    interviewerRole: 'HR' as const,
    parentQuestionId,
  })
  state.previous = [
    {
      stageId: 'first',
      stageName: '1차 면접',
      schedule: null,
      questions: [question('p1', null), question('pf1', 'p1'), question('p2', null)],
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
  // 처음 만든 질문만 Q번호가 붙는다 (꼬리질문은 번호를 세지 않는다)
  expect(screen.getByText('Q2. p2 지난 질문')).toBeInTheDocument()
  expect(screen.queryByText('pf1 지난 답')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /꼬리질문 1개 펼치기/ }))
  expect(screen.getByText('pf1 지난 답')).toBeInTheDocument()
  unmount()
  state.previous = []
})
