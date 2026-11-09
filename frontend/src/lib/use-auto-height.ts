import { useLayoutEffect, type RefObject } from 'react'

/**
 * 글이 길어지면 여러 줄 입력칸(textarea)의 높이를 글에 맞게 늘린다. maxHeight를 넘으면 그 높이에서 멈추고 안에서 스크롤한다.
 * 글을 지우면 다시 줄어든다. value가 바뀔 때마다 잰다.
 */
export function useAutoHeight(
  ref: RefObject<HTMLTextAreaElement | null>,
  value: string,
  maxHeight = 160,
) {
  useLayoutEffect(() => {
    const element = ref.current
    if (!element) return
    element.style.height = 'auto'
    const height = Math.min(element.scrollHeight, maxHeight)
    element.style.height = `${height}px`
    element.style.overflowY = element.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [ref, value, maxHeight])
}
