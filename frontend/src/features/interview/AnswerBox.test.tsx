import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AnswerBox, AUTOSAVE_MS } from './AnswerBox'
import { ApiError } from '@/lib/api/client'

const actions = vi.hoisted(() => ({
  answer: vi.fn(),
  suggest: vi.fn(),
  add: vi.fn(),
}))

vi.mock('@/features/interview/api', () => ({
  useInterviewActions: () => ({
    answer: { mutateAsync: actions.answer },
    suggestFollowUps: { mutateAsync: actions.suggest },
    addFollowUp: { isPending: false, mutate: actions.add },
  }),
}))

const question = {
  questionId: 'q1',
  version: 0,
  text: '정산 배치 개선에서 맡은 일',
  source: 'AI' as const,
  answer: '',
  reason: null,
  interviewerRole: 'PRACTICAL' as const,
  parentQuestionId: null,
}

function renderBox(answer = '') {
  return render(
    <div>
      <AnswerBox
        stageId="stage"
        applicationId="kim"
        question={{ ...question, answer }}
        editable
        canFollowUp
      />
      <button>다른 질문</button>
    </div>,
  )
}

const box = () => screen.getByLabelText('정산 배치 개선에서 맡은 일 답변')
const flush = () => act(async () => {})

beforeEach(() => {
  actions.answer.mockReset().mockResolvedValue({})
  actions.suggest.mockReset()
  actions.add.mockReset()
})

describe('💾 자동 저장', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('타이핑을 멈추고 2초 뒤 분석 없이 저장하고 저장됨을 보여 준다', async () => {
    renderBox()
    fireEvent.change(box(), { target: { value: '병렬로' } })
    fireEvent.change(box(), { target: { value: '병렬로 바꿨습니다' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS - 1))
    expect(actions.answer).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    await flush()
    expect(actions.answer).toHaveBeenCalledTimes(1)
    expect(actions.answer).toHaveBeenCalledWith({
      questionId: 'q1',
      answer: '병렬로 바꿨습니다',
      analyze: false,
      expectedVersion: 0,
    })
    expect(screen.getByText('저장됨')).toBeInTheDocument()
  })

  it('자동 저장된 답도 다른 질문으로 넘어가면 분석을 한 번 요청한다', async () => {
    renderBox()
    fireEvent.change(box(), { target: { value: '병렬로 바꿨습니다' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS))
    await flush()
    fireEvent.blur(box(), { relatedTarget: screen.getByRole('button', { name: '다른 질문' }) })
    await flush()
    expect(actions.answer).toHaveBeenLastCalledWith({
      questionId: 'q1',
      answer: '병렬로 바꿨습니다',
      analyze: true,
      expectedVersion: 0,
    })
    // 같은 답으로 다시 드나들면 보내지 않는다
    fireEvent.blur(box())
    await flush()
    expect(actions.answer).toHaveBeenCalledTimes(2)
  })

  it('바꾸지 않은 칸은 떠나도 저장하지 않는다', async () => {
    renderBox('이미 적은 답')
    fireEvent.blur(box())
    await flush()
    expect(actions.answer).not.toHaveBeenCalled()
  })

  it('저장 안 된 글이 있으면 페이지를 떠날 때 경고한다', () => {
    renderBox()
    fireEvent.change(box(), { target: { value: '아직 저장 전' } })
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })

  it('다음 자동 저장에는 앞선 응답의 최신 버전을 보낸다', async () => {
    actions.answer
      .mockResolvedValueOnce({ questions: [{ questionId: 'q1', version: 1 }] })
      .mockResolvedValueOnce({ questions: [{ questionId: 'q1', version: 2 }] })
    renderBox()
    fireEvent.change(box(), { target: { value: '첫 초안' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS))
    await flush()
    fireEvent.change(box(), { target: { value: '다음 초안' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS))
    await flush()
    expect(actions.answer).toHaveBeenLastCalledWith({
      questionId: 'q1',
      answer: '다음 초안',
      analyze: false,
      expectedVersion: 1,
    })
  })

  it('충돌하면 초안을 보존하고 오래된 버전으로 자동 재시도하지 않는다', async () => {
    actions.answer.mockRejectedValueOnce(new ApiError(409, 'ANSWER_CONFLICT', ''))
    renderBox()
    fireEvent.change(box(), { target: { value: '보존할 초안' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS))
    await flush()
    expect(screen.getByText('저장하지 못했어요')).toBeInTheDocument()
    fireEvent.change(box(), { target: { value: '추가로 작성한 초안' } })
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_MS))
    await flush()
    expect(actions.answer).toHaveBeenCalledTimes(1)
    expect(box()).toHaveValue('추가로 작성한 초안')
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
})

describe('🎤 꼬리질문', () => {
  it('답이 없으면 꼬리질문 받기 버튼이 없다', () => {
    renderBox()
    expect(screen.queryByRole('button', { name: '꼬리질문 받기' })).not.toBeInTheDocument()
  })

  it('답이 충분하면 추가로 확인할 점이 없다고 알려 준다', async () => {
    actions.suggest.mockResolvedValue({ needed: false, suggestions: [] })
    renderBox('충분한 답')
    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    expect(await screen.findByText('추가로 확인할 점이 없어요.')).toBeInTheDocument()
    expect(actions.suggest).toHaveBeenCalledWith({ questionId: 'q1', avoid: [] })
  })

  it('제안 2개 중 하나를 고르면 확인 포인트와 함께 꼬리질문으로 넣는다', async () => {
    actions.suggest.mockResolvedValue({
      needed: true,
      suggestions: [
        { text: '작업 단위는 어떻게 나눴나요?', check: '판단 기준이 없습니다.' },
        { text: '결과는 어떻게 확인했나요?', check: '검증 방법이 없습니다.' },
      ],
    })
    renderBox('병렬로 바꿨습니다')
    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    expect(await screen.findByText('확인 포인트 · 판단 기준이 없습니다.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /결과는 어떻게 확인했나요/ }))
    expect(actions.add).toHaveBeenCalledWith(
      {
        questionId: 'q1',
        text: '결과는 어떻게 확인했나요?',
        source: 'AI',
        check: '검증 방법이 없습니다.',
      },
      expect.any(Object),
    )
  })

  it('다시 제안은 한 번만, 앞서 본 제안을 빼고 받는다', async () => {
    const first = [{ text: 'A 질문', check: 'A' }]
    actions.suggest
      .mockResolvedValueOnce({ needed: true, suggestions: first })
      .mockResolvedValueOnce({ needed: true, suggestions: [{ text: 'B 질문', check: 'B' }] })
    renderBox('답')
    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    fireEvent.click(await screen.findByRole('button', { name: '다시 제안' }))
    expect(await screen.findByText('B 질문')).toBeInTheDocument()
    expect(actions.suggest).toHaveBeenLastCalledWith({ questionId: 'q1', avoid: ['A 질문'] })
    expect(screen.getByRole('button', { name: '다시 제안' })).toBeDisabled()
  })

  it('직접 쓴 꼬리질문은 확인 포인트 없이 넣고, 선택 안 함은 아무것도 저장하지 않는다', async () => {
    actions.suggest.mockResolvedValue({
      needed: true,
      suggestions: [{ text: 'A 질문', check: 'A' }],
    })
    renderBox('답')
    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    fireEvent.click(await screen.findByRole('button', { name: '선택 안 함' }))
    expect(actions.add).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '꼬리질문 받기' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    fireEvent.click(await screen.findByRole('button', { name: '직접 쓰기' }))
    fireEvent.change(screen.getByLabelText('직접 쓸 꼬리질문'), {
      target: { value: '그때 팀 규모는요?' },
    })
    fireEvent.click(screen.getByRole('button', { name: '추가' }))
    expect(actions.add).toHaveBeenCalledWith(
      { questionId: 'q1', text: '그때 팀 규모는요?', source: 'MANUAL', check: null },
      expect.any(Object),
    )
  })

  it('받기 전에 화면의 답을 분석 없이 먼저 저장한다', async () => {
    actions.suggest.mockResolvedValue({ needed: false, suggestions: [] })
    renderBox('처음 답')
    fireEvent.change(box(), { target: { value: '고친 답' } })
    fireEvent.click(screen.getByRole('button', { name: '꼬리질문 받기' }))
    await screen.findByText('추가로 확인할 점이 없어요.')
    expect(actions.answer).toHaveBeenCalledWith({
      questionId: 'q1',
      answer: '고친 답',
      analyze: false,
      expectedVersion: 0,
    })
    expect(actions.answer.mock.invocationCallOrder[0]).toBeLessThan(
      actions.suggest.mock.invocationCallOrder[0],
    )
  })
})
