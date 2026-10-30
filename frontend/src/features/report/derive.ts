// 부품이 그리는 값 중 묶음 값을 세어 만드는 것. ai derive.py와 같은 계산이라 문장 검사와 그림이 맞는다.
import type { Evidence, ReportBundle } from './types'

/** 있음 · 충족으로 세는 판정 값 */
export const POSITIVE = new Set(['MET', 'YES', 'PASS', 'CONFIRMED', 'RECOMMENDED'])

/** Python round()와 같은 반올림 (.5는 짝수 쪽). ai 검사가 계산한 숫자와 맞춘다 */
export function roundHalfEven(value: number) {
  const floor = Math.floor(value)
  const diff = value - floor
  if (Math.abs(diff - 0.5) > 1e-9) return Math.round(value)
  return floor % 2 === 0 ? floor : floor + 1
}

export function valuesOf(bundle: ReportBundle, key: string) {
  const values = new Map<string, number | string>()
  for (const fact of bundle.facts) if (fact.key === key) values.set(fact.applicant, fact.value)
  return values
}

/** 부품이 그리는 지원자 범위. 비교면 비교 대상, 아니면 전형 전체 */
export function scopeOf(bundle: ReportBundle) {
  return bundle.kind === 'COMPARE' ? bundle.targets : bundle.applicants.map((a) => a.number)
}

/** 두 판정 key의 (행 값, 열 값)별 인원. 'row|col' 꼴 key */
export function crossCounts(bundle: ReportBundle, rowKey: string, colKey: string) {
  const rows = valuesOf(bundle, rowKey)
  const cols = valuesOf(bundle, colKey)
  const counts = new Map<string, number>()
  for (const [number, row] of rows) {
    const col = cols.get(number)
    if (col === undefined) continue
    const cell = `${row}|${col}`
    counts.set(cell, (counts.get(cell) ?? 0) + 1)
  }
  return counts
}

function percent(values: Map<string, number | string>, people: string[]) {
  if (people.length === 0) return 0
  const positive = people.filter((number) => POSITIVE.has(String(values.get(number)))).length
  return roundHalfEven((100 * positive) / people.length)
}

/** key별 [그룹 비율 %, 전체 비율 %] */
export function sharePercents(
  bundle: ReportBundle,
  keys: string[],
  groupKey: string,
  groupValue: string,
) {
  const everyone = bundle.applicants.map((a) => a.number)
  const groups = valuesOf(bundle, groupKey)
  const group = everyone.filter((number) => groups.get(number) === groupValue)
  return new Map(
    keys.map((key) => {
      const values = valuesOf(bundle, key)
      return [key, [percent(values, group), percent(values, everyone)] as const]
    }),
  )
}

/** 판정 key의 값별 인원과 충족 · 있음 비율(%) */
export function tally(bundle: ReportBundle, key: string, people: string[]) {
  const values = valuesOf(bundle, key)
  const counts = new Map<string, number>()
  for (const number of people) {
    const value = values.get(number)
    if (value !== undefined) counts.set(String(value), (counts.get(String(value)) ?? 0) + 1)
  }
  const total = [...counts.values()].reduce((sum, count) => sum + count, 0)
  const met = [...counts].reduce(
    (sum, [value, count]) => sum + (POSITIVE.has(value) ? count : 0),
    0,
  )
  return { counts, rate: total ? roundHalfEven((100 * met) / total) : 0 }
}

/** 관점 도넛의 비율(%)과 아래 글. 숫자 key 하나면 점수 / 만점, 판정 key면 충족 · 있음 항목 비율 */
export function ringPercent(bundle: ReportBundle, keys: string[], applicant: string) {
  const facts = bundle.facts.filter((f) => f.applicant === applicant && keys.includes(f.key))
  if (facts.length !== keys.length) return null
  const [first] = facts
  if (keys.length === 1 && typeof first.value === 'number') {
    if (!first.max) return null
    return {
      pct: roundHalfEven((100 * first.value) / first.max),
      note: `${first.value}/${first.max}점`,
    }
  }
  if (facts.some((f) => typeof f.value === 'number')) return null
  const met = facts.filter((f) => POSITIVE.has(String(f.value))).length
  return { pct: roundHalfEven((100 * met) / keys.length), note: `충족 ${met}/${keys.length}` }
}

/** 칸 막대 하나. 점수는 10칸 중 채운 칸(점수 / 만점), 판정은 항목 수 중 충족 항목 수 */
export type Meter =
  | { kind: 'score'; value: number; max: number; filled: number; cells: number }
  | { kind: 'verdict'; met: number; filled: number; cells: number }

export const SCORE_CELLS = 10

/** 영역 점수처럼 만점이 있는 숫자 key 하나인 관점인가. 점수가 빈(보류) 지원자가 있어도 점수 표로 그린다 */
export function isScoreView(bundle: ReportBundle, keys: string[]) {
  return (
    keys.length === 1 &&
    bundle.facts.some((f) => f.key === keys[0] && typeof f.value === 'number' && !!f.max)
  )
}

/** ringPercent와 같은 값을 칸 막대로. 값이 모자라면 null */
export function meterOf(bundle: ReportBundle, keys: string[], applicant: string): Meter | null {
  const facts = bundle.facts.filter((f) => f.applicant === applicant && keys.includes(f.key))
  if (facts.length !== keys.length) return null
  const [first] = facts
  if (keys.length === 1 && typeof first.value === 'number') {
    if (!first.max) return null
    const filled = roundHalfEven((SCORE_CELLS * first.value) / first.max)
    return { kind: 'score', value: first.value, max: first.max, filled, cells: SCORE_CELLS }
  }
  if (facts.some((f) => typeof f.value === 'number')) return null
  const met = facts.filter((f) => POSITIVE.has(String(f.value))).length
  return { kind: 'verdict', met, filled: met, cells: keys.length }
}

/** 전형 전체에서 그 지원자 값이 상위 몇 %인지. 같은 값은 같은 위치 */
export function topPercent(bundle: ReportBundle, key: string, applicant: string) {
  const values = valuesOf(bundle, key)
  const mine = values.get(applicant)
  const numbers = [...values.values()].filter((v): v is number => typeof v === 'number')
  if (typeof mine !== 'number' || numbers.length === 0) return null
  const above = numbers.filter((v) => v > mine).length
  return Math.max(1, roundHalfEven((100 * (above + 1)) / numbers.length))
}

/** 근거를 화면에 나눠 보여 줄 조각. 항목(영역 · 이름 · 판정), AI 분석, 원문 */
export interface EvidenceParts {
  id: string
  area: string | null
  label: string | null
  verdict: string | null
  analysis: string
  quote: string | null
  source: string
  agent: string
}

/** 예전 리포트는 판단과 원문을 '판단 (원문: 문장)' 한 줄로 저장했다 */
const LEGACY_QUOTE = /^([\s\S]*?)\s*\(원문:\s*([\s\S]*)\)\s*$/

/**
 * 근거를 판단과 원문으로 나눈다. 예전 리포트는 한 줄에서 원문을 떼어 내고,
 * 서류 근거(e-지원자번호-항목)는 항목 이름 · 판정을 묶음 값에서 찾는다
 */
export function evidenceParts(bundle: ReportBundle, item: Evidence): EvidenceParts {
  let analysis = item.text
  let quote = item.quote ?? null
  const legacy = quote ? null : LEGACY_QUOTE.exec(item.text)
  if (legacy) {
    analysis = legacy[1]
    quote = legacy[2]
  }
  const criterion = item.id.slice(`e-${item.applicant}-`.length)
  const key = `document.criterion.${criterion}`
  const fact =
    item.agent === 'application'
      ? bundle.facts.find((f) => f.applicant === item.applicant && f.key === key)
      : undefined
  return {
    id: item.id,
    area: bundle.areas.find((area) => area.keys.includes(key))?.label ?? null,
    label: item.label ?? (fact ? fact.label.replace(/^\S+\s+/, '') : null),
    verdict: item.verdict ?? (typeof fact?.value === 'string' ? fact.value : null),
    analysis,
    quote,
    source: item.source,
    agent: item.agent,
  }
}
