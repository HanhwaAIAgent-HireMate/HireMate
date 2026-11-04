import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { useDragScroll } from './useDragScroll'

function List({ select }: { select: () => void }) {
  const { ref, dragging, handlers } = useDragScroll()
  return (
    <div ref={ref} {...handlers} role="region" aria-label="템플릿" data-dragging={dragging}>
      <button onClick={select}>템플릿 선택</button>
    </div>
  )
}

beforeEach(() => {
  vi.stubGlobal(
    'PointerEvent',
    class extends MouseEvent {
      readonly pointerId: number
      readonly pointerType: string
      constructor(type: string, options: PointerEventInit = {}) {
        super(type, options)
        this.pointerId = options.pointerId ?? 1
        this.pointerType = options.pointerType ?? 'mouse'
      }
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

it('카드를 끌면 좌우 스크롤되고 놓을 때 템플릿이 잘못 선택되지 않는다', () => {
  const select = vi.fn()
  render(<List select={select} />)
  const list = screen.getByRole('region', { name: '템플릿' })
  const button = screen.getByRole('button', { name: '템플릿 선택' })
  list.scrollLeft = 120
  fireEvent.pointerDown(button, { pointerId: 1, clientX: 200, clientY: 100, button: 0 })
  fireEvent.pointerMove(list, { pointerId: 1, clientX: 100, clientY: 101 })
  expect(list.scrollLeft).toBe(220)
  expect(list).toHaveAttribute('data-dragging', 'true')
  fireEvent.pointerUp(list, { pointerId: 1 })
  fireEvent.click(button, { detail: 1 })
  expect(select).not.toHaveBeenCalled()
  expect(list).toHaveAttribute('data-dragging', 'false')
  fireEvent.pointerDown(button, { pointerId: 2, clientX: 100, button: 0 })
  fireEvent.pointerUp(button, { pointerId: 2 })
  fireEvent.click(button, { detail: 1 })
  expect(select).toHaveBeenCalledOnce()
})

it('작은 손 움직임은 일반 클릭으로 처리하고 터치·키보드 사용을 유지한다', () => {
  const select = vi.fn()
  render(<List select={select} />)
  const list = screen.getByRole('region', { name: '템플릿' })
  const button = screen.getByRole('button', { name: '템플릿 선택' })
  fireEvent.pointerDown(button, { clientX: 100, button: 0 })
  fireEvent.pointerMove(list, { clientX: 103 })
  fireEvent.pointerUp(button)
  fireEvent.click(button, { detail: 1 })
  expect(select).toHaveBeenCalledOnce()
  fireEvent.pointerDown(button, { pointerType: 'touch', clientX: 100 })
  fireEvent.pointerMove(list, { pointerType: 'touch', clientX: 20 })
  expect(list.scrollLeft).toBe(0)
  fireEvent.click(button, { detail: 0 })
  expect(select).toHaveBeenCalledTimes(2)
})

it('드래그가 취소돼도 잡기 상태가 남지 않는다', () => {
  render(<List select={vi.fn()} />)
  const list = screen.getByRole('region', { name: '템플릿' })
  fireEvent.pointerDown(list, { clientX: 100, button: 0 })
  fireEvent.pointerMove(list, { clientX: 50 })
  fireEvent.pointerCancel(list)
  expect(list).toHaveAttribute('data-dragging', 'false')
})
