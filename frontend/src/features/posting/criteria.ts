import type {
  CriteriaRequest,
  CriterionDraft,
  CriterionInput,
  CriterionItem,
  ImportantAdvice,
  PostingContent,
  ScreeningCriteria,
} from '@/features/posting/api'

export type CriterionType = CriterionItem['criterion']['criterionType']
export type Category = CriterionItem['criterion']['category']
/** 평가 기준을 다는 목록. 공고 본문의 칸 이름이다 */
export type ListKey = 'qualifications' | 'preferred'

/** 공고 작성 화면의 서류 평가 칸. 게시 확인창에서 이 칸으로 바로 온다 */
export const SCREENING_ID = 'screening'

export const CRITERIA_LISTS: { key: ListKey; category: Category; label: string }[] = [
  { key: 'qualifications', category: 'QUALIFICATION', label: '자격 요건' },
  { key: 'preferred', category: 'PREFERENCE', label: '우대 사항' },
]

/** 항목 유형. 서류 평가 AI가 판정하는 방식이 달라진다 */
export const CRITERION_TYPES: { value: CriterionType; label: string; hint: string }[] = [
  { value: 'CONDITION', label: '조건형', hint: '경력 기간 · 자격증처럼 맞다 / 아니다로 판정해요' },
  { value: 'SINGLE', label: '단일 경험형', hint: '경험이 있다 / 없다로 판정해요' },
  {
    value: 'COMPOSITE',
    label: '복합 경험형',
    hint: '여러 부분이 있는 경험이라 일부만 있으면 부분 충족이에요',
  },
]

const MAX_RULE = 500
const MAX_CERTIFICATES = 10

/**
 * 항목 하나의 평가 기준 입력값. 화면에서는 자격 요건 · 우대 사항 줄마다 하나씩 둔다.
 * basis는 기준을 정할 때의 문장이다. 지금 문장과 다르면 기준을 다시 확인하라고 알린다.
 */
export type RuleForm = {
  important: boolean
  criterionType: CriterionType
  met: string
  partial: string
  unmet: string
  /** 화면에서는 쉼표로 나눠 한 칸에 쓴다 */
  certificates: string
  ncsUnitCode: string
  basis: string
}

export type RuleLists = Record<ListKey, RuleForm[]>
export type RuleProblems = Partial<Record<'met' | 'partial' | 'unmet' | 'certificates', string>>

export function emptyRule(): RuleForm {
  return {
    important: false,
    criterionType: 'SINGLE',
    met: '',
    partial: '',
    unmet: '',
    certificates: '',
    ncsUnitCode: '',
    basis: '',
  }
}

/** 무엇이든 입력한 기준. 저장할 때 이 항목만 보내고, 아무것도 없는 항목은 기준 없이 둔다 */
export function isFilled(rule: RuleForm) {
  return (
    rule.important ||
    [rule.met, rule.partial, rule.unmet, rule.certificates].some((text) => text.trim() !== '')
  )
}

/** 기준을 정한 뒤 문장이 바뀌었는지 */
export function isStale(rule: RuleForm, text: string) {
  return isFilled(rule) && rule.basis !== '' && rule.basis !== text.trim()
}

/** 공고 문장마다 저장한 기준을 문장으로 짝지어 입력값으로 바꾼다. 짝이 없는 줄은 빈 기준이다 */
export function rulesFor(
  content: Pick<PostingContent, ListKey>,
  criteria: ScreeningCriteria,
): RuleLists {
  const saved = (category: Category, text: string) =>
    criteria.items.find(
      (item) =>
        item.saved && item.criterion.category === category && item.criterion.text === text.trim(),
    )?.criterion
  const rules = {} as RuleLists
  for (const { key, category } of CRITERIA_LISTS) {
    rules[key] = content[key].map((text) => {
      const criterion = saved(category, text)
      if (!criterion) return emptyRule()
      return {
        important: criterion.important,
        criterionType: criterion.criterionType,
        met: criterion.evaluationRules.met,
        partial: criterion.evaluationRules.partial ?? '',
        unmet: criterion.evaluationRules.unmet,
        certificates: criterion.certificates.join(', '),
        ncsUnitCode: criterion.ncsUnitCode ?? '',
        basis: text.trim(),
      }
    })
  }
  return rules
}

/** 입력한 기준에서 비거나 너무 긴 칸. 아무것도 입력하지 않은 기준은 문제가 없다 */
export function ruleProblems(rule: RuleForm): RuleProblems {
  if (!isFilled(rule)) return {}
  const problems: RuleProblems = {}
  if (!rule.met.trim()) problems.met = '충족 기준을 써 주세요'
  if (!rule.unmet.trim()) problems.unmet = '미충족 기준을 써 주세요'
  if (rule.criterionType === 'COMPOSITE' && !rule.partial.trim()) {
    problems.partial = '부분 충족 기준을 써 주세요'
  }
  for (const field of ['met', 'partial', 'unmet'] as const) {
    if (rule[field].length > MAX_RULE) problems[field] = `${MAX_RULE}자까지 쓸 수 있어요`
  }
  if (splitCertificates(rule.certificates).length > MAX_CERTIFICATES) {
    problems.certificates = `자격증은 ${MAX_CERTIFICATES}개까지예요`
  }
  return problems
}

export function hireCountProblem(value: string): string | null {
  if (!value.trim()) return '선발 인원을 입력해 주세요'
  const count = Number(value)
  if (!Number.isInteger(count) || count < 1) return '선발 인원은 1명 이상 정수예요'
  if (count > 1000) return '선발 인원은 1000명까지예요'
  return null
}

/**
 * 저장 요청. 문장이 있고 기준을 입력한 줄만 보낸다. 같은 목록에 같은 문장이 둘이면 앞의 것만 보낸다.
 * 문장은 앞뒤 공백을 떼어 공고 저장(빈 줄 · 공백 정리)과 같게 맞춘다.
 */
export function toCriteriaRequest(
  hireCount: number,
  content: Pick<PostingContent, ListKey>,
  rules: RuleLists,
): CriteriaRequest {
  const criteria: CriterionInput[] = []
  for (const { key, category } of CRITERIA_LISTS) {
    const seen = new Set<string>()
    content[key].forEach((line, index) => {
      const text = line.trim()
      const rule = rules[key][index]
      if (!text || !rule || !isFilled(rule) || seen.has(text)) return
      seen.add(text)
      criteria.push({
        category,
        text,
        important: rule.important,
        criterionType: rule.criterionType,
        met: rule.met.trim(),
        // 부분 충족은 복합 경험형에만 있다
        partial: rule.criterionType === 'COMPOSITE' ? rule.partial.trim() : '',
        unmet: rule.unmet.trim(),
        certificates: splitCertificates(rule.certificates),
        ncsUnitCode: rule.ncsUnitCode.trim(),
      })
    })
  }
  return { hireCount, criteria }
}

/** 문장이 빈 줄의 기준을 뺀다. 공고를 저장하면 빈 줄이 빠져서 줄 순서를 맞춘다 */
export function compactRules(content: Pick<PostingContent, ListKey>, rules: RuleLists): RuleLists {
  const compact = (key: ListKey) =>
    content[key].flatMap((text, i) => (text.trim() ? [rules[key][i] ?? emptyRule()] : []))
  return { qualifications: compact('qualifications'), preferred: compact('preferred') }
}

/** AI 초안을 기준에 넣는다. '중요'는 목록 단위로 따로 추천해서 여기서 바꾸지 않는다 */
export function draftRule(rule: RuleForm, draft: CriterionDraft, text: string): RuleForm {
  return {
    ...rule,
    criterionType: draft.criterionType,
    met: draft.met,
    partial: draft.partial ?? '',
    unmet: draft.unmet,
    certificates: draft.certificates.join(', '),
    basis: text.trim(),
  }
}

/** '중요' 추천을 목록 안 순서 → 근거 주요 업무로 */
export function recommendedDuties(advice: ImportantAdvice, key: ListKey) {
  return new Map(advice[key].map((pick) => [pick.index, pick.duty]))
}

export function splitCertificates(text: string) {
  return text
    .split(/[,\n]/)
    .map((name) => name.trim())
    .filter(Boolean)
}
