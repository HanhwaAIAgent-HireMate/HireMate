// Report Agent 결과 타입. ai의 ReportBundle(camelCase)과 ReportSpec(부품 설계서)을 그대로 옮겼다.
// backend 연동(2단계)에서 schema.d.ts 타입으로 바꾼다.

export type ReportKind = 'STAGE' | 'COMPARE' | 'FINAL'

export interface BundleStage {
  stageId: string
  name: string
  type: string
  confirmedAt: string | null
}

export interface BundleApplicant {
  number: string
  careerYears: number | null
  lastCompany: string | null
}

export interface Metric {
  id: string
  stageId: string | null
  label: string
  value: number
  unit: string
  key?: string | null
  group?: string | null
}

export interface Fact {
  id: string
  applicant: string
  stageId: string
  key: string
  label: string
  value: number | string
  max?: number | null
}

/** 근거 하나. text는 분석 Agent의 판단(AI 분석), quote는 원문 문장 그대로다 */
export interface Evidence {
  id: string
  applicant: string
  stageId: string
  agent: string
  text: string
  source: string
  quote?: string | null
  label?: string | null
  verdict?: string | null
  /** 원문의 강도. QUANT는 성과를 숫자와 단위로 적은 문장, CLAIM은 한 일만 적은 문장이다 */
  strength?: 'QUANT' | 'CLAIM' | null
}

export interface Area {
  id: string
  label: string
  scoreKey: string | null
  keys: string[]
}

export interface ReportBundle {
  kind: ReportKind
  stageId: string
  title: string
  asOf: string
  focus: string
  brief: boolean
  stages: BundleStage[]
  applicants: BundleApplicant[]
  targets: string[]
  totalKey: string | null
  areas: Area[]
  metrics: Metric[]
  facts: Fact[]
  evidence: Evidence[]
}

interface Titled {
  title: string
  caption?: string
}

export type Block =
  | (Titled & { type: 'kpi'; metrics: string[] })
  | (Titled & { type: 'bar'; keys: string[]; applicants: string[]; reference?: string[] })
  | (Titled & { type: 'stacked'; keys: string[]; applicants: string[] })
  | (Titled & { type: 'radar'; keys: string[]; applicants: string[] })
  | (Titled & {
      type: 'distribution'
      key: string
      highlight?: string[]
      reference?: string[]
      split?: string | null
    })
  | (Titled & { type: 'donut'; metrics: string[] })
  | (Titled & { type: 'cross'; rowKey: string; colKey: string })
  | (Titled & { type: 'share'; keys: string[]; groupKey: string; groupValue: string })
  | (Titled & { type: 'composition'; rows: { label: string; metrics: string[] }[] })
  | (Titled & { type: 'position'; keys: string[]; applicants: string[] })
  | (Titled & { type: 'rings'; views: { label: string; keys: string[] }[]; applicants: string[] })
  | (Titled & { type: 'matrix'; keys: string[]; applicants: string[] })
  | (Titled & { type: 'tally'; keys: string[]; applicants?: string[]; by: 'key' | 'applicant' })
  | (Titled & { type: 'table'; keys: string[]; applicants: string[] })
  | {
      type: 'evidence'
      title: string
      items: { applicant: string; keywords?: string[]; text: string; evidence: string[] }[]
    }
  | { type: 'text'; title: string; text: string; evidence: string[] }

export type BlockType = Block['type']

export interface Section {
  title: string
  area?: string | null
  takeaway: string
  blocks: Block[]
}

/** 비교 대상끼리 판정이 갈린 항목 하나와 그 이유 (AI가 서류 분석 세부를 읽고 쓴 문장, 판정만 적은 문장이면 코드가 쓴 것) */
export interface Split {
  key: string
  text: string
  evidence: string[]
}

export interface ReportSpec {
  title: string
  summary: string
  skills: string[]
  sections: Section[]
  /** 비교 리포트만. 예전 리포트에는 없다 */
  splits?: Split[]
}

/** 리포트 한 건. backend가 지원자번호 → 이름(names)을 붙여 준다. 실행 기록은 화면 위 칩으로 보여 준다 */
export interface ReportView {
  bundle: ReportBundle
  spec: ReportSpec
  names: Record<string, string>
  skills: string[]
  fallback: boolean
  /** AI 작업 과정 (읽은 자료, 검사 횟수, 코드가 고친 것). 예전 리포트는 비어 있다 */
  steps: string[]
}
