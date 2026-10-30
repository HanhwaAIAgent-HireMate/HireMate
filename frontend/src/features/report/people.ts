import { useEffect, useState } from 'react'
import { flushSync } from 'react-dom'

// 리포트의 지원자 표기. 웹 화면은 '이름(지원자번호)'로, PDF · 외부 내보내기는 지원자번호만 보여 준다.
// 모델이 쓴 문장에는 지원자번호만 있으므로 화면에서 이름을 붙인다

const NUMBER = /(?<![A-Za-z0-9])[A-Z]-\d{3,}(?!\d)/g

export const NO_NAMES: Record<string, string> = {}

/** 지원자 한 명의 표기. 이름이 없으면 지원자번호만 */
export function whoOf(names: Record<string, string>, number: string) {
  const name = names[number]
  return name ? `${name}(${number})` : number
}

/** 문장 속 지원자번호를 '이름(지원자번호)'로 바꾼다. 이름을 모르는 번호는 그대로 둔다 */
export function withNames(text: string, names: Record<string, string>) {
  return text.replace(NUMBER, (number) => whoOf(names, number))
}

/**
 * 화면에 쓸 이름표. 인쇄(PDF 저장) 중에는 빈 이름표를 돌려줘 지원자번호만 보이게 한다.
 * 인쇄 직전(beforeprint)에 바로 다시 그려야 인쇄본에 반영되므로 flushSync로 바꾼다
 */
export function useShownNames(names: Record<string, string>) {
  const printing = usePrinting()
  return printing ? NO_NAMES : names
}

export function usePrinting() {
  const [printing, setPrinting] = useState(false)
  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true))
    const after = () => setPrinting(false)
    window.addEventListener('beforeprint', before)
    window.addEventListener('afterprint', after)
    return () => {
      window.removeEventListener('beforeprint', before)
      window.removeEventListener('afterprint', after)
    }
  }, [])
  return printing
}
