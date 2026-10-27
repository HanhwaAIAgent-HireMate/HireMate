import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LiveSteps, StepsSummary } from './ChatSteps'

const STEPS = [
  '요청을 확인하고 있어요',
  '조건에 맞는 지원자를 찾고 있어요',
  '후보 3명을 다시 확인하고 있어요',
]

describe('처리 단계', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('진행 중에는 지난 단계를 모두 보이고 마지막 단계를 지금 단계로 표시한다', () => {
    vi.useFakeTimers()
    render(<LiveSteps steps={STEPS} />)

    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(STEPS)
    expect(screen.getByText(STEPS[2]).closest('li')).toHaveAttribute('aria-current', 'step')
    expect(screen.getByText(STEPS[0]).closest('li')).not.toHaveAttribute('aria-current')
    expect(screen.getByText('0초')).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('3초')).toBeInTheDocument()
  })

  it('답에는 단계 수와 걸린 시간만 보이고 누르면 단계 전체를 펼친다', () => {
    render(<StepsSummary steps={STEPS} seconds={12} />)
    const toggle = screen.getByRole('button', { name: /처리 과정 3단계/ })

    expect(toggle).toHaveTextContent('12초')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()

    fireEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getAllByRole('listitem').map((item) => item.textContent)).toEqual(STEPS)
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
