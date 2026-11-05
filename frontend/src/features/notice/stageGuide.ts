import type { StageGuide, StageGuideView } from '@/features/notice/api'

export type GuideMethod = NonNullable<StageGuide['method']>

export const METHOD_LABELS: Record<GuideMethod, string> = { ONLINE: '온라인', OFFLINE: '오프라인' }

/** backend StageGuideRequest와 같은 길이 */
export const PLACE_MAX = 500
export const PREPARATION_MAX = 500
export const NOTE_MAX = 1000

/** 일정을 정할 수 있는 범위. 앞 · 뒤 전형 중 일정을 정한 가장 가까운 전형이다 */
export type ScheduleBounds = {
  before?: { name: string; date: string }
  after?: { name: string; date: string }
}

export type GuideProblems = Partial<Record<'schedule' | 'place', string>>

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/

/** 이 컴퓨터 기준 오늘 (YYYY-MM-DD) */
export function todayIso(now = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

/** 지금 시각을 HH:mm으로. 오늘로 정한 시작 시각이 지났는지 볼 때 쓴다 */
export function nowTime(now = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(now.getHours())}:${pad(now.getMinutes())}`
}

/** YYYY-MM-DD에 날짜를 더한다 */
export function addDays(date: string, days: number) {
  const [year, month, day] = date.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

export function isHttpUrl(value: string) {
  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && Boolean(url.hostname)
  } catch {
    return false
  }
}

/** 저장해 둔 다른 전형의 일정으로 이 전형 일정의 범위를 정한다. views는 전형 순서대로다 */
export function scheduleBounds(views: StageGuideView[], stageId: string): ScheduleBounds {
  const index = views.findIndex((view) => view.stageId === stageId)
  const dated = (view: StageGuideView) =>
    view.guide.schedule ? { name: view.name, date: view.guide.schedule } : undefined
  const before = views.slice(0, index).reverse().map(dated).find(Boolean)
  const after = views
    .slice(index + 1)
    .map(dated)
    .find(Boolean)
  return { before, after }
}

/** 날짜 선택기에서 고를 수 있는 가장 이른 날과 늦은 날. 오늘보다 앞이거나 앞 전형과 같은 날은 고를 수 없다 */
export function scheduleRange(bounds: ScheduleBounds, today: string) {
  const afterBefore = bounds.before ? addDays(bounds.before.date, 1) : today
  return {
    min: afterBefore > today ? afterBefore : today,
    max: bounds.after ? addDays(bounds.after.date, -1) : undefined,
  }
}

/**
 * 저장하면 안 되는 입력. 일정은 바꿨을 때만 오늘 이후인지 보고(이미 지난 전형의 안내도 고칠 수 있게),
 * 앞 전형보다 뒤 · 다음 전형보다 앞이어야 한다. 장소는 진행 방식을 고른 뒤에 쓰고,
 * 온라인이면 http:// 또는 https:// 주소, 오프라인이면 꼭 쓴다
 */
export function guideProblems(
  draft: StageGuide,
  saved: StageGuide,
  bounds: ScheduleBounds,
  today: string,
  now?: string,
): GuideProblems {
  const problems: GuideProblems = {}
  const { schedule } = draft
  const time = draft.time?.slice(0, 5)
  const timeChanged = schedule !== saved.schedule || time !== saved.time?.slice(0, 5)
  if (schedule && !ISO_DATE.test(schedule)) {
    problems.schedule = '날짜를 다시 골라 주세요.'
  } else if (schedule && schedule !== saved.schedule && schedule < today) {
    problems.schedule = '지난 날짜는 고를 수 없어요.'
  } else if (schedule === today && time && now && timeChanged && time <= now) {
    problems.schedule = '지난 시간은 고를 수 없어요.'
  } else if (schedule && bounds.before && schedule <= bounds.before.date) {
    problems.schedule = `앞 전형(${bounds.before.name}, ${bounds.before.date})보다 뒤 날짜를 골라 주세요.`
  } else if (schedule && bounds.after && schedule >= bounds.after.date) {
    problems.schedule = `다음 전형(${bounds.after.name}, ${bounds.after.date})보다 앞 날짜를 골라 주세요.`
  }
  const place = draft.place.trim()
  if (!draft.method && place) {
    problems.place = '진행 방식을 먼저 골라 주세요.'
  } else if (draft.method === 'ONLINE' && place && !isHttpUrl(place)) {
    problems.place = 'http:// 또는 https://로 시작하는 주소를 넣어 주세요.'
  } else if (draft.method === 'OFFLINE' && !place) {
    problems.place = '오프라인이면 장소를 꼭 넣어 주세요.'
  }
  return problems
}

/** 비어 있는 칸 이름. 메일에서 빠지는 칸이라 게시 · 발송 전에 경고한다 (기타 안내는 선택이라 빼고 본다) */
export function missingGuideFields(guide: StageGuide) {
  return [
    !guide.schedule && '일정',
    !guide.method && '진행 방식',
    !guide.place.trim() && '장소·접속 링크',
    !guide.preparation.trim() && '준비 사항',
  ].filter((label): label is string => Boolean(label))
}
