import { describe, expect, it } from 'vitest'

import { isTooLight, MAIL_COLORS, normalizeColor } from './mailColor'

describe('normalizeColor', () => {
  it('앞의 #를 빼거나 대문자로 넣어도 #rrggbb로 맞춘다', () => {
    expect(normalizeColor('0055A4')).toBe('#0055a4')
    expect(normalizeColor(' #0055a4 ')).toBe('#0055a4')
  })

  it('6자리 색 코드가 아니면 받지 않는다', () => {
    expect(normalizeColor('#12345')).toBeNull()
    expect(normalizeColor('red')).toBeNull()
    expect(normalizeColor('#0055a4ff')).toBeNull()
  })
})

describe('isTooLight', () => {
  it('노란색 · 연한 하늘색처럼 흰 바탕에서 안 보이는 색은 밝다고 알린다', () => {
    expect(isTooLight('#ffeb3b')).toBe(true)
    expect(isTooLight('#a5d8ff')).toBe(true)
  })

  it('추천 색은 모두 흰 바탕에서 잘 보인다', () => {
    for (const color of MAIL_COLORS) expect(isTooLight(color.value)).toBe(false)
  })
})
