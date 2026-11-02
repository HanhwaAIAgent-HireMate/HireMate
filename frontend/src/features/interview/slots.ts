import type { InterviewAssignment } from '@/features/interview/sessions'

type SessionStatus = InterviewAssignment['status']

/** 면접 시간 한 칸: 같은 일시의 지원자는 한 면접으로 함께 본다. scheduledAt이 없으면 일정 미정 칸이다 */
export type InterviewSlot<T> = {
  key: string
  scheduledAt: string | null
  items: T[]
}

/** 같은 순간인지 비교할 열쇠. 서버가 보낸 표기(밀리초 자릿수 등)가 달라도 같은 시각이면 같다 */
export const slotKey = (scheduledAt: string | null) =>
  scheduledAt ? String(Date.parse(scheduledAt)) : 'unscheduled'

/** 지원자를 면접 일시별로 나눈다. 일시 순이고, 일정 미정은 맨 뒤다. 칸 안은 받은 순서를 지킨다 */
export function interviewSlots<T>(
  items: T[],
  scheduledAtOf: (item: T) => string | null | undefined,
): InterviewSlot<T>[] {
  const slots = new Map<string, InterviewSlot<T>>()
  for (const item of items) {
    const at = scheduledAtOf(item) ?? null
    const key = slotKey(at)
    const slot = slots.get(key) ?? { key, scheduledAt: at, items: [] }
    slot.items.push(item)
    slots.set(key, slot)
  }
  return [...slots.values()].sort((a, b) =>
    a.scheduledAt === null
      ? 1
      : b.scheduledAt === null
        ? -1
        : Date.parse(a.scheduledAt) - Date.parse(b.scheduledAt),
  )
}

/**
 * 면접 시간 한 칸의 상태 (서버의 InterviewGroups.status와 같다). 한 명이라도 진행 중이면 진행 중, 불참을 뺀 모두가
 * 끝났으면 종료, 모두 불참이면 불참, 그 밖에는 예정이다.
 */
export function slotStatus(statuses: SessionStatus[]): SessionStatus {
  const present = statuses.filter((status) => status !== 'ABSENT')
  if (present.includes('IN_PROGRESS')) return 'IN_PROGRESS'
  if (present.length === 0) return statuses.length > 0 ? 'ABSENT' : 'SCHEDULED'
  return present.every((status) => status === 'ENDED') ? 'ENDED' : 'SCHEDULED'
}
