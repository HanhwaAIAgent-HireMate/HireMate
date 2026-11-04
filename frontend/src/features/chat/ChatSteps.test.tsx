import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LiveSteps, StepsSummary } from './ChatSteps'

const STEPS = [
  { text: '요청을 확인하고 있어요', depth: 0 },
  { text: '조건에 맞는 지원자를 찾고 있어요', depth: 0 },
  { text: '후보 3명을 다시 확인하고 있어요', depth: 0 },
]

const NESTED = [
  { text: '요청을 확인하고 있어요', depth: 0 },
  { text: '요청에 맞는 답변을 준비하고 있어요', depth: 0 },
  { text: '정유민의 프로필을 읽고 있어요', depth: 1 },
  { text: '서류 Agent · 정유민의 제출 문서 2건을 검토하고 있어요', depth: 1 },
  { text: '근거 문장 3개를 찾았어요', depth: 2 },
]

/** Root 단계 줄. 점의 상태(done, running)와 함께 읽는다 */
const rootLines = () =>
  screen.getAllByTestId('root-step').map((item) => ({
    text: item.querySelector('[data-step-text]')?.textContent ?? '',
    state: item.querySelector('[data-dot]')?.getAttribute('data-dot'),
  }))

describe('처리 단계', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('진행 중에는 Root 단계를 세로선 위의 점으로 쌓고 마지막 단계만 진행 중으로 표시한다', () => {
    vi.useFakeTimers()
    render(<LiveSteps steps={STEPS} />)

    expect(rootLines()).toEqual([
      { text: STEPS[0].text, state: 'done' },
      { text: STEPS[1].text, state: 'done' },
      { text: STEPS[2].text, state: 'running' },
    ])
    expect(screen.getAllByTestId('root-step')[2]).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText('0초')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('3초')).toBeInTheDocument()
  })

  it('진행 중인 Root 단계 아래에는 지금 하는 일 한 줄과 그 결과만 보인다', () => {
    render(<LiveSteps steps={NESTED} />)

    const running = screen.getAllByTestId('root-step')[1]
    expect(running).toHaveAttribute('aria-current', 'step')
    const below = within(running)
    expect(below.getByText('서류 Agent')).toHaveAttribute('data-agent')
    expect(below.getByText('정유민의 제출 문서 2건을 검토하고 있어요')).toBeInTheDocument()
    expect(below.getByText('근거 문장 3개를 찾았어요')).toBeInTheDocument()
    expect(below.getAllByTestId('sub-step')).toHaveLength(2)
    expect(below.queryByText(/앞서 한 일/)).not.toBeInTheDocument()
    expect(below.queryByText('정유민의 프로필을 읽고 있어요')).not.toBeInTheDocument()
    // 끝난 Root 단계 아래에는 하위 일을 보이지 않는다
    expect(within(screen.getAllByTestId('root-step')[0]).queryAllByTestId('sub-step')).toHaveLength(
      0,
    )
  })

  it('하위 단계는 깊이와 상관없이 한 칸만 들여 쓴다', () => {
    const { container } = render(<StepsSummary steps={NESTED} seconds={12} />)
    fireEvent.click(screen.getByRole('button', { name: /처리 과정 2단계/ }))

    expect(container.querySelector('ol ol ol')).toBeNull()
  })

  it('답에는 Root 단계 수와 걸린 시간만 보이고 누르면 모든 하위 일까지 펼친다', () => {
    render(<StepsSummary steps={NESTED} seconds={12} />)
    const toggle = screen.getByRole('button', { name: /처리 과정 2단계/ })

    expect(toggle).toHaveTextContent('12초')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('root-step')).not.toBeInTheDocument()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(rootLines()).toEqual([
      { text: NESTED[0].text, state: 'done' },
      { text: NESTED[1].text, state: 'done' },
    ])
    expect(screen.getAllByTestId('sub-step').map((item) => item.textContent)).toEqual([
      '정유민의 프로필을 읽고 있어요',
      '서류 Agent정유민의 제출 문서 2건을 검토하고 있어요',
      '근거 문장 3개를 찾았어요',
    ])
    // 끝난 답이라 지금 단계로 표시하는 줄이 없다
    expect(
      screen.getAllByTestId('root-step').some((item) => item.hasAttribute('aria-current')),
    ).toBe(false)

    fireEvent.click(toggle)
    expect(screen.queryByTestId('root-step')).not.toBeInTheDocument()
  })

  it('걸린 시간을 모르면 단계 수만 보이고, 단계가 없는 예전 기록은 아무것도 그리지 않는다', () => {
    const { container, rerender } = render(<StepsSummary steps={STEPS} seconds={null} />)
    expect(screen.getByRole('button')).toHaveTextContent(/^처리 과정 3단계$/)

    rerender(<StepsSummary steps={[]} seconds={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
