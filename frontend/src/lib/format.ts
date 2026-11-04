const WEEKDAYS = ['일', '월', '화', '수', '목', '금', '토']

function pad(value: number) {
  return String(value).padStart(2, '0')
}

/** 10.12 (월) */
export function formatDate(value: string | Date) {
  const date = new Date(value)
  return `${pad(date.getMonth() + 1)}.${pad(date.getDate())} (${WEEKDAYS[date.getDay()]})`
}

/** 10.12 (월) 09:00 */
export function formatDateTime(value: string | Date) {
  const date = new Date(value)
  return `${formatDate(date)} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 10.23 21:14 */
export function formatShortDateTime(value: string | Date) {
  const date = new Date(value)
  return `${pad(date.getMonth() + 1)}.${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/** 10.26 */
export function formatMonthDay(value: string | Date) {
  const date = new Date(value)
  return `${pad(date.getMonth() + 1)}.${pad(date.getDate())}`
}

/** 마감까지 남은 날. 오늘 마감이면 D-Day. */
export function dDay(value: string | Date, now = new Date()) {
  const end = new Date(value)
  const startOfDay = (date: Date) =>
    new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const days = Math.round((startOfDay(end) - startOfDay(now)) / 86_400_000)
  return days > 0 ? `D-${days}` : days === 0 ? 'D-Day' : '마감'
}

/** datetime-local 입력값 (로컬 시간) */
export function toLocalInput(date: Date) {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

/**
 * 낱말 뒤에 '로' 또는 '으로'를 붙인다. 받침이 없거나 ㄹ 받침이면 '로', 그 밖의 받침은 '으로'.
 * 한글로 끝나지 않으면(영문 · 숫자) 받침을 알 수 없어 '(으)로'를 붙인다.
 * 예: 직무역량 평가로, 최종 면접으로, 1차 실무면접으로, 서류 전형으로, 코딩테스트로
 */
export function withRo(word: string) {
  const last = word.trimEnd().at(-1)
  if (!last) return word
  const code = last.charCodeAt(0) - 0xac00
  if (code < 0 || code > 11171) return `${word}(으)로`
  const final = code % 28
  return final === 0 || final === 8 ? `${word}로` : `${word}으로`
}
