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
