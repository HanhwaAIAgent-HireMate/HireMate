import type { ReportDistribution } from './api'

type Criterion = ReportDistribution['criteria'][number]

export const percent = (part: number, whole: number) =>
  whole > 0 ? Math.round((100 * part) / whole) : 0

/** 판정 인원 합 */
export const judged = (criterion: Criterion) =>
  criterion.met + criterion.partial + criterion.notMet + criterion.unknown

/** 충족이 아닌 판정(미충족 · 부분 충족 · 확인 필요) 비율 */
export const issueRate = (criterion: Criterion) =>
  percent(criterion.partial + criterion.notMet + criterion.unknown, judged(criterion))

const shortText = (text: string) => (text.length > 24 ? `${text.slice(0, 24)}…` : text)

/** 맨 위 요약. 모델 없이 숫자로 만든 문장이다 */
export function insightLines(data: ReportDistribution): string[] {
  const lines: string[] = []
  const gap = data.aboveLine - data.target
  if (gap > 0) {
    lines.push(
      `필수 조건을 모두 충족한 ${data.aboveLine}명이 목표 ${data.target}명보다 ${gap}명 많아요.` +
        (data.cut
          ? ` 충족 ${data.cut.value}개인 ${data.cut.to - data.cut.from + 1}명 사이에서 선발이 갈려요.`
          : ''),
    )
  } else if (gap < 0) {
    lines.push(
      `필수 조건을 모두 충족한 사람이 ${data.aboveLine}명으로 목표 ${data.target}명에 ${-gap}명 모자라요. 필수 조건을 못 채운 사람 중 다시 볼 사람을 먼저 보세요.`,
    )
  } else {
    lines.push(`필수 조건을 모두 충족한 ${data.aboveLine}명이 목표 ${data.target}명과 같아요.`)
  }
  // 화면의 '많이 걸리는 필수 조건'과 같은 기준(충족이 아닌 판정 비율)으로 고른다
  const required = data.criteria
    .filter((criterion) => criterion.required && judged(criterion) > 0)
    .sort((a, b) => issueRate(b) - issueRate(a))[0]
  if (required && issueRate(required) > 0) {
    const whole = judged(required)
    lines.push(
      `가장 많이 걸리는 필수 조건은 ${required.criterionId} '${shortText(required.text)}'이에요. ` +
        `${issueRate(required)}%가 충족이 아니에요(미충족 · 부분 ${percent(required.notMet + required.partial, whole)}%, ` +
        `확인 필요 ${percent(required.unknown, whole)}%).`,
    )
  }
  const unclear = data.criteria
    .filter((criterion) => judged(criterion) > 0 && criterion !== required)
    .map((criterion) => ({ criterion, rate: percent(criterion.unknown, judged(criterion)) }))
    .sort((a, b) => b.rate - a.rate)[0]
  if (unclear && unclear.rate >= 20) {
    lines.push(
      `${unclear.criterion.criterionId} '${shortText(unclear.criterion.text)}'은 ${unclear.rate}%가 확인 필요라 서류만으로 판단하기 어려운 항목이에요.`,
    )
  }
  const passed = data.passed ?? 0
  if (passed > data.target) {
    lines.push(
      `합격 처리 ${passed}명으로 목표 ${data.target}명보다 ${passed - data.target}명 많아요. 목표는 참고값이라 합격을 막지 않아요.`,
    )
  } else if (passed > 0) {
    lines.push(
      `합격 처리 ${passed}명으로 목표 ${data.target}명까지 ${data.target - passed}명 남았어요.`,
    )
  }
  if (data.analyzed < data.total) {
    lines.push(`${data.total - data.analyzed}명은 아직 분석 전이라 확인 필요로 셌어요.`)
  }
  return lines
}
