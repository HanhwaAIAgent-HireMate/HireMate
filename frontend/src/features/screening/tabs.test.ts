import { describe, expect, it } from 'vitest'

import { neighborTab, pickTab } from '@/features/screening/tabs'

const tabs = [{ id: 't1' }, { id: 't2' }, { id: 't3' }]

describe('pickTab', () => {
  it('주소의 탭이 있으면 그 탭을 연다', () => {
    expect(pickTab(tabs, 't2')).toBe('t2')
  })

  it('주소에 탭이 없거나 지워진 탭이면 첫 탭을 연다', () => {
    expect(pickTab(tabs, null)).toBe('t1')
    expect(pickTab(tabs, 'gone')).toBe('t1')
  })

  it('탭이 없으면(시작하지 않은 전형) 열 탭이 없다', () => {
    expect(pickTab([], 't1')).toBeNull()
  })
})

describe('neighborTab', () => {
  it('지운 탭의 다음 탭으로, 마지막 탭이면 앞 탭으로 옮긴다', () => {
    expect(neighborTab(tabs, 't2')).toBe('t3')
    expect(neighborTab(tabs, 't3')).toBe('t2')
  })
})
