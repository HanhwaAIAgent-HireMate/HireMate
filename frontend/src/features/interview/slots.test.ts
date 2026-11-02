import { describe, expect, it } from 'vitest'

import { interviewSlots, slotKey, slotStatus } from '@/features/interview/slots'

describe('면접 시간 칸', () => {
  it('같은 일시의 지원자를 한 칸으로 묶고 일시 순으로 두며 일정 미정은 맨 뒤에 둔다', () => {
    const rows = [
      { id: 'a', at: '2026-11-03T05:00:00Z' },
      { id: 'b', at: null },
      { id: 'c', at: '2026-11-02T03:00:00Z' },
      { id: 'd', at: '2026-11-03T05:00:00.000Z' },
    ]
    const slots = interviewSlots(rows, (row) => row.at)
    expect(slots.map((slot) => slot.items.map((row) => row.id))).toEqual([['c'], ['a', 'd'], ['b']])
    expect(slots[2].scheduledAt).toBeNull()
    expect(slotKey('2026-11-03T05:00:00Z')).toBe(slotKey('2026-11-03T05:00:00.000Z'))
  })

  it('한 명이라도 진행 중이면 진행 중, 불참을 뺀 모두가 끝나면 종료로 본다', () => {
    expect(slotStatus(['SCHEDULED', 'ABSENT'])).toBe('SCHEDULED')
    expect(slotStatus(['IN_PROGRESS', 'ABSENT', 'IN_PROGRESS'])).toBe('IN_PROGRESS')
    expect(slotStatus(['ENDED', 'ABSENT'])).toBe('ENDED')
    expect(slotStatus(['ABSENT', 'ABSENT'])).toBe('ABSENT')
  })
})
