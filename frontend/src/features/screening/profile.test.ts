import { describe, expect, it } from 'vitest'

import {
  agentLabel,
  categoryLabel,
  countByVerification,
  filterByVerification,
  verificationLabel,
} from '@/features/screening/profile'

const items = [
  { content: '금융 (카드 결제 · 정산)', verification: 'EVIDENCED' as const },
  { content: '대용량 트래픽 처리 수치 확인 필요', verification: 'UNCONFIRMED' as const },
  { content: '장애 대응 당번으로 승인 서버를 직접 운영', verification: 'CONFIRMED' as const },
  { content: '정산 배치 개선에서 맡은 역할이 서류와 다름', verification: 'CONFLICT' as const },
  { content: 'Java, Spring Boot', verification: 'EVIDENCED' as const },
]

describe('countByVerification', () => {
  it('확인 상태별 항목 수와 전체 수를 센다', () => {
    expect(countByVerification(items)).toEqual({
      ALL: 5,
      CONFIRMED: 1,
      EVIDENCED: 2,
      UNCONFIRMED: 1,
      CONFLICT: 1,
    })
    expect(countByVerification([]).ALL).toBe(0)
  })
})

describe('filterByVerification', () => {
  it('고른 확인 상태의 항목만 순서대로 남기고, 전체면 그대로 둔다', () => {
    expect(filterByVerification(items, 'EVIDENCED').map((item) => item.content)).toEqual([
      '금융 (카드 결제 · 정산)',
      'Java, Spring Boot',
    ])
    expect(filterByVerification(items, 'ALL')).toBe(items)
  })
})

describe('labels', () => {
  it('확인 상태 · 분류 · 분석 단계를 한글로 보여 주고, 모르는 값은 그대로 둔다', () => {
    expect(verificationLabel('CONFLICT')).toBe('상충')
    expect(categoryLabel('DOMAIN')).toBe('도메인')
    expect(categoryLabel('NEW_KIND')).toBe('NEW_KIND')
    expect(agentLabel('interview')).toBe('면접 분석')
  })
})
