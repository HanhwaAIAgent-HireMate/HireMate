import { describe, expect, it } from 'vitest'

import {
  crossCounts,
  itemNames,
  ringPercent,
  roundHalfEven,
  sharePercents,
  tally,
  topPercent,
  withItemNames,
} from './derive'
import type { Fact, ReportBundle } from './types'

function fact(applicant: string, key: string, value: number | string, max?: number): Fact {
  return { id: `${applicant}-${key}`, applicant, stageId: 's', key, label: key, value, max }
}

const bundle: ReportBundle = {
  kind: 'COMPARE',
  stageId: 's',
  title: '백엔드 개발자',
  asOf: '2026-10-27T14:20:00Z',
  focus: '',
  brief: false,
  stages: [],
  applicants: ['A-0001', 'A-0002', 'A-0003', 'A-0004'].map((number) => ({
    number,
    careerYears: 3,
    lastCompany: null,
  })),
  targets: ['A-0001', 'A-0002'],
  totalKey: 'document.total',
  areas: [],
  metrics: [],
  facts: [
    fact('A-0001', 'document.total', 90, 100),
    fact('A-0002', 'document.total', 60, 100),
    fact('A-0003', 'document.total', 60, 100),
    fact('A-0004', 'document.total', 30, 100),
    fact('A-0001', 'q1', 'MET'),
    fact('A-0001', 'q2', 'PARTIAL'),
    fact('A-0002', 'q1', 'MET'),
    fact('A-0002', 'q2', 'MET'),
    fact('A-0001', 'decision', 'PASS'),
    fact('A-0002', 'decision', 'FAIL'),
    fact('A-0003', 'decision', 'PASS'),
    fact('A-0004', 'decision', 'FAIL'),
    fact('A-0001', 'ai', 'RECOMMENDED'),
    fact('A-0002', 'ai', 'RECOMMENDED'),
    fact('A-0003', 'ai', 'NOT_RECOMMENDED'),
    fact('A-0004', 'ai', 'NOT_RECOMMENDED'),
    fact('A-0001', 'skill', 'YES'),
    fact('A-0002', 'skill', 'NO'),
    fact('A-0003', 'skill', 'YES'),
    fact('A-0004', 'skill', 'YES'),
  ],
  evidence: [],
}

describe('리포트 부품 계산 (ai derive.py와 같은 결과)', () => {
  it('반올림은 Python처럼 .5를 짝수 쪽으로 보낸다', () => {
    expect(roundHalfEven(12.5)).toBe(12)
    expect(roundHalfEven(13.5)).toBe(14)
    expect(roundHalfEven(66.67)).toBe(67)
  })

  it('관점 도넛은 점수 / 만점, 판정이면 충족 항목 비율이다', () => {
    expect(ringPercent(bundle, ['document.total'], 'A-0002')).toEqual({ pct: 60, note: '60/100점' })
    expect(ringPercent(bundle, ['q1', 'q2'], 'A-0001')).toEqual({ pct: 50, note: '충족 1/2' })
    expect(ringPercent(bundle, ['q1', 'missing'], 'A-0001')).toBeNull()
  })

  it('교차표는 두 판정의 인원을 센다', () => {
    const counts = crossCounts(bundle, 'ai', 'decision')
    expect(counts.get('RECOMMENDED|PASS')).toBe(1)
    expect(counts.get('NOT_RECOMMENDED|PASS')).toBe(1)
    expect(counts.get('RECOMMENDED|FAIL')).toBe(1)
  })

  it('비율 막대는 그룹과 전체의 있음 비율을 견준다', () => {
    expect(sharePercents(bundle, ['skill'], 'decision', 'PASS').get('skill')).toEqual([100, 75])
  })

  it('판정 비율과 상위 %를 센다', () => {
    expect(tally(bundle, 'q2', ['A-0001', 'A-0002']).rate).toBe(50)
    expect(topPercent(bundle, 'document.total', 'A-0001')).toBe(25)
    expect(topPercent(bundle, 'document.total', 'A-0003')).toBe(50)
  })
})

describe('항목 이름', () => {
  const labelled: ReportBundle = {
    ...bundle,
    facts: [
      {
        ...fact('A-1', 'document.criterion.Q-01', 'MET'),
        label: 'Q-01 Java 또는 Kotlin 기반 서버 개발 경력 3년 이상',
      },
      { ...fact('A-1', 'document.criterion.P-04', 'MET'), label: 'P-04 CI/CD 구성' },
    ],
  }

  it('문장 속 항목 코드 옆에 짧은 항목 이름을 붙인다', () => {
    const names = itemNames(labelled)
    expect(withItemNames('Q-01과 P-04가 갈렸어요.', names)).toBe(
      'Q-01(Java 또는 Kotlin 기…)과 P-04(CI/CD 구성)가 갈렸어요.',
    )
  })

  it('이름이 이미 붙은 코드와 모르는 코드, 지원자번호는 그대로 둔다', () => {
    const names = itemNames(labelled)
    expect(withItemNames('Q-01(Java 경력)과 Q-09, A-0001', names)).toBe(
      'Q-01(Java 경력)과 Q-09, A-0001',
    )
  })
})
