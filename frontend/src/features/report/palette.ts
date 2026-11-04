// 리포트 색. 채도를 낮춘 팔레트다. 지원자 앞 3색은 색약 · 대비 검사(all-pairs)를 통과했고, 4 · 5번째는 비교 5명까지 겹치지 않게 더한 색이다.
// 판정 색은 늘 아이콘과 글자를 함께 붙여 색만으로 구분하지 않는다.

export const INK = '#22262B'
export const SUB = '#5C6168'
export const MUTED = '#8B9099'
export const GRID = '#EEF0F3'

/** 비교 대상 고정 색. 리포트 안 모든 부품에서 같은 지원자는 같은 색이다 */
export const PEOPLE = ['#3D6DB5', '#D0703C', '#2C9B7B', '#8E5EA8', '#B38A1E']
/** 쌓은 막대의 영역 (한 hue의 단계) */
export const PARTS = ['#4A5F86', '#A9B8D3', '#D6DDEA']
/** 순서가 있는 값 (경력 구간, 상위 %) */
export const SEQ = ['#E6EAF2', '#C4CFE2', '#98ABCC', '#6A84B2', '#465F8C']
/** 도넛 조각 */
export const SLICES = ['#6F9C85', '#D6A096', '#C8C5BE', '#98ABCC', '#DCC28A']
/** 분포를 결정으로 나눠 칠할 때 */
export const SPLIT: Record<string, string> = { PASS: '#6F9C85', FAIL: '#E8D5D0' }

export interface Status {
  label: string
  icon: string
  bg: string
  fg: string
  bar: string
}

/** 판정 칩 · 비율 막대 색 */
export const STATUS: Record<string, Status> = {
  MET: { label: '충족', icon: '✓', bg: '#E4EFE8', fg: '#2F6B4C', bar: '#8DB89F' },
  PARTIAL: { label: '부분', icon: '◐', bg: '#F6EDD9', fg: '#7A5A1E', bar: '#DCC28A' },
  NOT_MET: { label: '미충족', icon: '✕', bg: '#F5E3DF', fg: '#8E3F33', bar: '#D6A096' },
  UNKNOWN: { label: '보류', icon: '?', bg: '#EEEDEA', fg: '#5F5E5A', bar: '#C8C5BE' },
  CONFIRMED: { label: '확인됨', icon: '✓', bg: '#E4EFE8', fg: '#2F6B4C', bar: '#8DB89F' },
  NOT_CONFIRMED: { label: '미확인', icon: '?', bg: '#EEEDEA', fg: '#5F5E5A', bar: '#C8C5BE' },
}

/** 판정 칩이 없는 값(결정 · AI 추천 · 있음)의 비율 막대 색 */
const VALUE_BAR: Record<string, string> = {
  PASS: '#8DB89F',
  FAIL: '#D6A096',
  PENDING: '#C8C5BE',
  RECOMMENDED: '#98ABCC',
  NOT_RECOMMENDED: '#C8C5BE',
  YES: '#8DB89F',
  NO: '#C8C5BE',
}

/** 비율 막대 한 칸의 이름과 색 */
export function valueBand(value: string, index: number) {
  const status = STATUS[value]
  return {
    label: status ? `${status.icon} ${status.label}` : word(value),
    color: status?.bar ?? VALUE_BAR[value] ?? SLICES[index % SLICES.length],
  }
}

const WORDS: Record<string, string> = {
  PASS: '합격',
  FAIL: '불합격',
  RECOMMENDED: 'AI 추천',
  NOT_RECOMMENDED: '추천 밖',
  YES: '있음',
  NO: '없음',
}

/** 판정 값을 화면 말로 */
export function word(value: string) {
  return WORDS[value] ?? STATUS[value]?.label ?? value
}
