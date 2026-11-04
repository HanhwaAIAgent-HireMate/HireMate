import { describe, expect, it } from 'vitest'

import { chartFor, withoutCommonPrefix, type ChartContext } from './charts'
import type { Block, Fact, ReportBundle } from './types'

function fact(applicant: string, value: number): Fact {
  return {
    id: applicant,
    applicant,
    stageId: 's',
    key: 'document.total',
    label: '서류 총점',
    value,
    max: 100,
  }
}

const bundle: ReportBundle = {
  kind: 'COMPARE',
  stageId: 's',
  title: '백엔드 개발자',
  asOf: '2026-11-01T05:15:00Z',
  focus: '',
  brief: false,
  stages: [],
  applicants: ['A-0001', 'A-0002', 'A-0003'].map((number) => ({
    number,
    careerYears: 3,
    lastCompany: null,
  })),
  targets: ['A-0001', 'A-0002', 'A-0003'],
  totalKey: 'document.total',
  areas: [],
  metrics: [
    {
      id: 'm1',
      stageId: 's',
      label: '서류 총점 평균',
      value: 69,
      unit: '점',
      key: 'document.total',
    },
  ],
  facts: [fact('A-0001', 79), fact('A-0002', 82), fact('A-0003', 79)],
  evidence: [],
}

const names: Record<string, string> = { 'A-0001': '김도현', 'A-0002': '이서윤', 'A-0003': '박지훈' }
const ctx: ChartContext = {
  bundle,
  name: (number) => names[number] ?? null,
  who: (number) => `${names[number]}(${number})`,
  color: () => '#3E72C4',
}

const block: Block = {
  type: 'distribution',
  title: '전체 지원자 분포',
  key: 'document.total',
  highlight: ['A-0002', 'A-0001', 'A-0003'],
  reference: ['m1'],
}

interface Mark {
  xAxis: number
  label: { formatter: string; distance: number }
}

function marks(): Mark[] {
  const { option } = chartFor(block, ctx)
  const series = (option as { series: { markLine?: { data: Mark[] } }[] }).series
  return series.find((s) => s.markLine)?.markLine?.data ?? []
}

describe('분포 차트 기준선', () => {
  it('같은 값의 지원자는 기준선 하나에 이름을 이어 쓴다', () => {
    const at79 = marks().filter((mark) => mark.xAxis === 79)

    expect(at79).toHaveLength(1)
    expect(at79[0].label.formatter).toBe('김도현(A-0001) · 박지훈(A-0003)')
  })

  it('가까이 붙은 기준선은 이름표를 다른 높이에 둔다', () => {
    const distances = marks().map((mark) => mark.label.distance)

    expect(new Set(distances).size).toBe(distances.length)
  })

  it('이름표를 올린 만큼 차트 위 여백과 높이를 늘린다', () => {
    const { height } = chartFor(block, ctx)

    expect(height).toBeGreaterThan(250)
  })
})

describe('도넛 조각 이름', () => {
  it('같은 앞 낱말은 빼고, 같은 앞부분이 없으면 그대로 둔다', () => {
    expect(withoutCommonPrefix(['최종 합격자 신입', '최종 합격자 7년 이상'])).toEqual([
      '신입',
      '7년 이상',
    ])
    expect(withoutCommonPrefix(['충족', '미충족'])).toEqual(['충족', '미충족'])
    // 이름이 모두 같은 앞부분뿐이면 빈 이름이 되지 않게 그대로 둔다
    expect(withoutCommonPrefix(['전체', '전체'])).toEqual(['전체', '전체'])
  })
})
