import { useState } from 'react'
import { toast } from 'sonner'

import {
  useDraftCriterion,
  useRecommendImportant,
  useSaveScreeningCriteria,
  type PostingContent,
  type ScreeningCriteria,
} from '@/features/posting/api'
import {
  compactRules,
  CRITERIA_LISTS,
  draftRule,
  emptyRule,
  hireCountProblem,
  isFilled,
  recommendedDuties,
  ruleProblems,
  rulesFor,
  toCriteriaRequest,
  type ListKey,
  type RuleForm,
  type RuleLists,
  type RuleProblems,
} from '@/features/posting/criteria'
import { errorMessage } from '@/lib/api/client'

type Lists<T> = Record<ListKey, T>
type Texts = Pick<PostingContent, ListKey>

/** index 줄의 기준을 바꾼다. 목록이 줄보다 짧으면 빈 기준으로 채운다 */
function replaceAt(list: RuleForm[], index: number, change: (rule: RuleForm) => RuleForm) {
  const next = [...list]
  while (next.length <= index) next.push(emptyRule())
  next[index] = change(next[index])
  return next
}

const noProblems = (): Lists<RuleProblems[]> => ({ qualifications: [], preferred: [] })
const noDuties = (): Lists<Map<number, string>> => ({
  qualifications: new Map(),
  preferred: new Map(),
})

/** 문장이 있고 기준을 입력한 줄 수 */
export function filledCount(texts: Texts, rules: RuleLists) {
  return CRITERIA_LISTS.reduce(
    (sum, { key }) =>
      sum +
      texts[key].filter((text, i) => text.trim() && isFilled(rules[key][i] ?? emptyRule())).length,
    0,
  )
}

/**
 * 공고 작성 화면의 서류 평가 기준. 자격 요건 · 우대 사항 줄마다 기준을 두고, 줄을 더하거나 빼면 기준도 같이 움직인다.
 * 저장할 때 문장과 함께 보내 서버는 문장으로 짝을 맞춘다. AI 초안은 입력 칸만 채우고 저장하지 않는다.
 *
 * 저장한 직후처럼 화면이 다시 그려지기 전에 부르는 함수는 기준 목록(current)을 직접 받는다.
 */
export function useRequirementCriteria(
  recruitmentId: string,
  initial: { content: PostingContent; criteria: ScreeningCriteria },
) {
  const save = useSaveScreeningCriteria(recruitmentId)
  const draft = useDraftCriterion(recruitmentId)
  const recommend = useRecommendImportant(recruitmentId)
  const [rules, setRules] = useState<RuleLists>(() => rulesFor(initial.content, initial.criteria))
  const [hireCount, setHireCount] = useState(initial.criteria.hireCount?.toString() ?? '')
  /** 서버에 기준이나 선발 인원을 저장한 적이 있는지. 있으면 모두 지울 때도 저장해야 한다 */
  const [stored, setStored] = useState(initial.criteria.criteriaVersion !== null)
  const [dirty, setDirty] = useState(false)
  const [problems, setProblems] = useState(noProblems)
  const [hireProblem, setHireProblem] = useState<string | null>(null)
  /** '중요' 추천의 근거 주요 업무. 목록 안 순서 → 문장 */
  const [duties, setDuties] = useState(noDuties)
  const [drafting, setDrafting] = useState<{ key: ListKey; index: number } | null>(null)
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null)
  /** AI 초안을 받았으면 연습용 AI인지. 받기 전에는 null */
  const [stub, setStub] = useState<boolean | null>(null)
  const busy = progress !== null || drafting !== null || save.isPending

  const clearProblem = (key: ListKey, index: number) =>
    setProblems((current) => ({
      ...current,
      [key]: current[key].map((old, i) => (i === index ? {} : old)),
    }))

  /** 줄을 더하거나 뺄 때 기준 목록을 맞춘다. 빈 줄이라 저장할 것은 바뀌지 않는다 */
  const moveRows = (key: ListKey, next: RuleForm[]) => {
    setRules((current) => ({ ...current, [key]: next }))
    setProblems((current) => ({ ...current, [key]: [] }))
    setDuties((current) => ({ ...current, [key]: new Map() }))
  }

  const changeRule = (key: ListKey, index: number, rule: RuleForm, text: string) => {
    setRules((current) => ({
      ...current,
      [key]: replaceAt(current[key], index, () => ({ ...rule, basis: text.trim() })),
    }))
    clearProblem(key, index)
    setDirty(true)
  }

  const changeHireCount = (value: string) => {
    setHireCount(value)
    setHireProblem(null)
    setDirty(true)
  }

  /** 저장할 것이 있는지. 입력한 기준이나 선발 인원이 있거나, 저장한 적이 있으면 저장한다 */
  const needsSave = (texts: Texts, current: RuleLists) =>
    dirty && (stored || hireCount.trim() !== '' || filledCount(texts, current) > 0)

  /** 저장 전에 칸을 검사해 문제를 표시한다. 문제가 없으면 true다 */
  const validate = (texts: Texts) => {
    if (!needsSave(texts, rules)) return true
    const found = {} as Lists<RuleProblems[]>
    for (const { key } of CRITERIA_LISTS) {
      found[key] = texts[key].map((text, i) =>
        text.trim() ? ruleProblems(rules[key][i] ?? emptyRule()) : {},
      )
    }
    const hire = hireCountProblem(hireCount)
    setProblems(found)
    setHireProblem(hire)
    return (
      !hire &&
      CRITERIA_LISTS.every(({ key }) => found[key].every((p) => Object.keys(p).length === 0))
    )
  }

  /** 공고를 저장하면 빈 줄이 빠져서, 같은 줄의 기준도 빼 순서를 맞춘다. 맞춘 기준을 돌려준다 */
  const compact = (texts: Texts) => {
    const next = compactRules(texts, rules)
    setRules(next)
    setProblems(noProblems())
    setDuties(noDuties())
    return next
  }

  /** 저장한 공고 문장과 기준을 함께 저장한다. 저장할 것이 없으면 그대로 true다 */
  const saveCriteria = async (texts: Texts, current: RuleLists) => {
    if (!needsSave(texts, current)) {
      setDirty(false)
      return true
    }
    try {
      await save.mutateAsync(toCriteriaRequest(Number(hireCount), texts, current))
      setStored(true)
      setDirty(false)
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }

  /** AI 수정안을 적용하거나 되돌려 문장이 바뀌면, 저장한 기준으로 다시 짝짓는다 */
  const reset = (content: PostingContent, criteria: ScreeningCriteria) => {
    setRules(rulesFor(content, criteria))
    setProblems(noProblems())
    setDuties(noDuties())
  }

  /** 저장한 공고의 한 줄에 AI 초안을 받는다. 유형 · 판정 기준 · 자격증만 바꾸고 '중요'는 그대로 둔다 */
  const fillOne = async (key: ListKey, index: number, text: string) => {
    const category = key === 'qualifications' ? 'QUALIFICATION' : 'PREFERENCE'
    setDrafting({ key, index })
    try {
      const answer = await draft.mutateAsync({ category, text: text.trim() })
      setRules((current) => ({
        ...current,
        [key]: replaceAt(current[key], index, (rule) => draftRule(rule, answer.draft, text)),
      }))
      clearProblem(key, index)
      setStub(answer.stub)
      setDirty(true)
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    } finally {
      setDrafting(null)
    }
  }

  /**
   * 저장한 공고에서 기준이 비어 있는 줄만 채운다. 먼저 목록마다 '중요'를 추천받고, 줄마다 차례로 초안을 받는다.
   * content는 저장한 공고, current는 그에 맞춘 기준이라 줄 순서가 서버와 같다.
   */
  const fillAll = async (content: Texts, current: RuleLists) => {
    const targets = CRITERIA_LISTS.flatMap(({ key }) =>
      content[key].flatMap((text, index) =>
        text.trim() && !isFilled(current[key][index] ?? emptyRule()) ? [{ key, index, text }] : [],
      ),
    )
    if (targets.length === 0) {
      toast.info('기준이 비어 있는 항목이 없어요. 줄마다 [AI 초안]으로 다시 쓸 수 있어요.')
      return
    }
    const total = targets.length + 1
    setProgress({ done: 0, total })
    try {
      const answer = await recommend.mutateAsync()
      const recommended = {
        qualifications: recommendedDuties(answer.advice, 'qualifications'),
        preferred: recommendedDuties(answer.advice, 'preferred'),
      }
      setDuties(recommended)
      setStub(answer.stub)
      setRules((latest) => {
        const next = { ...latest }
        for (const { key, index } of targets) {
          next[key] = replaceAt(next[key], index, (rule) => ({
            ...rule,
            important: recommended[key].has(index),
          }))
        }
        return next
      })
      setDirty(true)
    } catch (error) {
      toast.error(errorMessage(error))
    }
    let completed = true
    for (const [order, { key, index, text }] of targets.entries()) {
      setProgress({ done: order + 1, total })
      if (!(await fillOne(key, index, text))) {
        completed = false
        break
      }
    }
    setProgress(null)
    if (completed) toast.success('AI 초안을 채웠어요. 확인하고 고친 뒤 저장해 주세요.')
  }

  return {
    rules,
    hireCount,
    dirty,
    problems,
    hireProblem,
    duties,
    drafting,
    progress,
    stub,
    busy,
    moveRows,
    changeRule,
    changeHireCount,
    validate,
    compact,
    save: saveCriteria,
    reset,
    fillOne,
    fillAll,
  }
}
