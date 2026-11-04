import { useRef, useState, type DragEvent, type MouseEvent, type PointerEvent } from 'react'

/** 짧은 클릭은 카드에 전달하고 가로로 끌면 목록만 이동한다. 터치는 브라우저 스크롤을 쓴다. */
export function useDragScroll() {
  const ref = useRef<HTMLDivElement>(null)
  const gesture = useRef<{
    id: number
    x: number
    y: number
    left: number
    moving: boolean
  } | null>(null)
  const suppressClick = useRef(false)
  const [dragging, setDragging] = useState(false)

  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (gesture.current?.id !== event.pointerId) return
    gesture.current = null
    setDragging(false)
    if (event.currentTarget.hasPointerCapture?.(event.pointerId))
      event.currentTarget.releasePointerCapture(event.pointerId)
  }

  return {
    ref,
    dragging,
    handlers: {
      onPointerDownCapture: (event: PointerEvent<HTMLDivElement>) => {
        if (!event.currentTarget.contains(event.target as Node)) return
        suppressClick.current = false
        if (event.button !== 0 || event.pointerType !== 'mouse') return
        gesture.current = {
          id: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          left: event.currentTarget.scrollLeft,
          moving: false,
        }
      },
      onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
        const start = gesture.current
        if (!start || start.id !== event.pointerId) return
        const delta = event.clientX - start.x
        if (!start.moving) {
          if (
            Math.abs(event.clientY - start.y) > Math.abs(delta) &&
            Math.abs(event.clientY - start.y) > 8
          ) {
            gesture.current = null
            return
          }
          if (Math.abs(delta) < 8) return
          start.moving = true
          suppressClick.current = true
          event.currentTarget.setPointerCapture?.(event.pointerId)
          setDragging(true)
        }
        event.preventDefault()
        event.currentTarget.scrollLeft = start.left - delta
      },
      onPointerUp: finish,
      onPointerCancel: finish,
      onLostPointerCapture: finish,
      onClickCapture: (event: MouseEvent<HTMLDivElement>) => {
        if (suppressClick.current && event.detail !== 0) {
          event.preventDefault()
          event.stopPropagation()
        }
      },
      onDragStart: (event: DragEvent<HTMLDivElement>) => event.preventDefault(),
    },
  }
}
