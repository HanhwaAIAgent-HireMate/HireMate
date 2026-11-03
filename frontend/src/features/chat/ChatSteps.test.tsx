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

/** 줄마다 자기 문구만 읽는다. 위 단계 줄의 textContent에는 아래 단계 문구도 들어 있다 */
const lineTexts = () =>
  screen
    .getAllByRole('listitem')
    .map((item) => item.querySelector(':scope > div')?.textContent ?? '')

describe('처리 단계', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('진행 중에는 지난 단계를 모두 보이고 마지막 단계를 지금 단계로 표시한다', () => {
    vi.useFakeTimers()
    render(<LiveSteps steps={STEPS} />)

    expect(lineTexts()).toEqual(STEPS.map((step) => step.text))
    expect(screen.getByText(STEPS[2].text).closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText(STEPS[0].text).closest('li')).not.toHaveAttribute('aria-current')
    expect(screen.getByText('0초')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('3초')).toBeInTheDocument()
  })

  it('하위 Agent와 도구의 단계는 Root 단계 아래 목록으로 들여 보이고, 지금 단계는 가장 깊은 단계다', () => {
    render(<LiveSteps steps={NESTED} />)

    const preparing = screen.getByText('요청에 맞는 답변을 준비하고 있어요').closest('li')
    expect(preparing).not.toBeNull()
    const below = within(preparing as HTMLElement)
    expect(below.getByText('정유민의 프로필을 읽고 있어요')).toBeInTheDocument()
    const agent = below
      .getByText('서류 Agent · 정유민의 제출 문서 2건을 검토하고 있어요')
      .closest('li')
    expect(within(agent as HTMLElement).getByText('근거 문장 3개를 찾았어요')).toBeInTheDocument()
    expect(screen.getByText('근거 문장 3개를 찾았어요').closest('li')).toHaveAttribute(
      'aria-current',
      'step',
    )
    expect(preparing).not.toHaveAttribute('aria-current')
  })

  it('답에는 Root 단계 수와 걸린 시간만 보이고 누르면 하위 단계까지 펼친다', () => {
    render(<StepsSummary steps={NESTED} seconds={12} />)
    const toggle = screen.getByRole('button', { name: /처리 과정 2단계/ })

    expect(toggle).toHaveTextContent('12초')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(lineTexts()).toEqual(NESTED.map((step) => step.text))
    // 끝난 답이라 지금 단계로 표시하는 줄이 없다
    expect(screen.getAllByRole('listitem').some((item) => item.hasAttribute('aria-current'))).toBe(
      false,
    )

    fireEvent.click(toggle)
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('걸린 시간을 모르면 단계 수만 보이고, 단계가 없는 예전 기록은 아무것도 그리지 않는다', () => {
    const { container, rerender } = render(<StepsSummary steps={STEPS} seconds={null} />)
    expect(screen.getByRole('button')).toHaveTextContent(/^처리 과정 3단계$/)

    rerender(<StepsSummary steps={[]} seconds={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})
