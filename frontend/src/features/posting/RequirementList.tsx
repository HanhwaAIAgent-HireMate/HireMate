import { ChevronDown, ChevronRight, Lock, Sparkles } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { AgentChip } from '@/features/posting/AiRequestPanel'
import {
  CRITERION_TYPES,
  emptyRule,
  isFilled,
  isStale,
  SCREENING_ID,
  type RuleForm,
  type RuleProblems,
} from '@/features/posting/criteria'
import { cn } from '@/lib/utils'

/**
 * 자격 요건 · 우대 사항 목록. 한 줄에 한 항목을 쓰고(Enter로 줄을 나누고 빈 줄에서 Backspace로 지운다),
 * 줄마다 서류 평가 기준을 접어 둔다. 줄을 더하거나 빼면 기준도 같이 움직인다.
 */
export function RequirementList({
  label,
  texts,
  rules,
  onChange,
  onRuleChange,
  locked,
  problems,
  duties,
  drafting,
  busy,
  onDraft,
}: {
  label: string
  texts: string[]
  rules: RuleForm[]
  /** rules는 줄을 더하거나 뺄 때만 온다. 글자만 바뀌면 기준은 그 줄에 그대로 있다 */
  onChange: (texts: string[], rules?: RuleForm[]) => void
  onRuleChange: (index: number, rule: RuleForm) => void
  /** 게시한 뒤라 문장과 기준을 바꿀 수 없다 */
  locked: boolean
  problems: RuleProblems[]
  /** '중요' 추천 근거. 줄 순서 → 주요 업무 문장 */
  duties: Map<number, string>
  /** 지금 AI 초안을 받는 줄 */
  drafting: number | null
  busy: boolean
  onDraft: (index: number) => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const rows = texts.length === 0 ? [''] : texts
  const ruleAt = (index: number) => rules[index] ?? emptyRule()
  const [opened, setOpened] = useState<Set<number>>(new Set())

  const focusRow = (index: number) =>
    requestAnimationFrame(() => {
      const inputs = container.current?.querySelectorAll<HTMLInputElement>('input[data-row]')
      inputs?.[index]?.focus()
    })

  const toggle = (index: number) =>
    setOpened((current) => {
      const next = new Set(current)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })

  return (
    <div ref={container} className="space-y-1">
      {rows.map((row, index) => {
        const rule = ruleAt(index)
        const problem = problems[index] ?? {}
        const open = opened.has(index) || Object.keys(problem).length > 0 || drafting === index
        return (
          <div key={index} className="rounded">
            <div className="flex items-baseline gap-2 px-1 text-sm">
              <span className="text-muted-foreground">·</span>
              <input
                data-row
                aria-label={`${label} ${index + 1}`}
                value={row}
                disabled={locked || busy}
                placeholder={index === 0 ? '내용을 입력해 주세요' : undefined}
                onChange={(event) =>
                  onChange(rows.map((old, i) => (i === index ? event.target.value : old)))
                }
                onKeyDown={(event) => {
                  if (event.nativeEvent.isComposing) return
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    onChange(
                      [...rows.slice(0, index + 1), '', ...rows.slice(index + 1)],
                      [
                        ...rows.slice(0, index + 1).map((_, i) => ruleAt(i)),
                        emptyRule(),
                        ...rows.slice(index + 1).map((_, i) => ruleAt(index + 1 + i)),
                      ],
                    )
                    focusRow(index + 1)
                  } else if (event.key === 'Backspace' && row === '' && rows.length > 1) {
                    event.preventDefault()
                    onChange(
                      rows.filter((_, i) => i !== index),
                      rows.flatMap((_, i) => (i === index ? [] : [ruleAt(i)])),
                    )
                    focusRow(Math.max(0, index - 1))
                  }
                }}
                className="min-w-0 flex-1 bg-transparent py-1 outline-none placeholder:text-muted-foreground disabled:cursor-default"
              />
              {row.trim() && (
                <button
                  type="button"
                  aria-expanded={open}
                  aria-label={`${label} ${index + 1} 평가 기준`}
                  onClick={() => toggle(index)}
                  className="flex shrink-0 items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs text-muted-foreground hover:text-foreground"
                >
                  {open ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
                  <RuleSummary rule={rule} stale={isStale(rule, row)} />
                </button>
              )}
            </div>
            {row.trim() && open && (
              <CriterionFields
                name={`${label} ${index + 1}`}
                rule={rule}
                stale={isStale(rule, row)}
                problems={problem}
                duty={duties.get(index)}
                locked={locked}
                busy={busy}
                drafting={drafting === index}
                onChange={(next) => onRuleChange(index, next)}
                onDraft={() => onDraft(index)}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

function RuleSummary({ rule, stale }: { rule: RuleForm; stale: boolean }) {
  if (!isFilled(rule)) return <span>평가 기준 없음</span>
  const type = CRITERION_TYPES.find((option) => option.value === rule.criterionType)
  return (
    <span className={cn(stale && 'text-amber-700')}>
      {rule.important && <span className="font-semibold text-foreground">★ 중요 · </span>}
      {type?.label}
      {stale && ' · 확인 필요'}
    </span>
  )
}

/** 한 줄의 평가 기준 입력. 지원자에게는 보이지 않는다 */
function CriterionFields({
  name,
  rule,
  stale,
  problems,
  duty,
  locked,
  busy,
  drafting,
  onChange,
  onDraft,
}: {
  name: string
  rule: RuleForm
  stale: boolean
  problems: RuleProblems
  duty?: string
  locked: boolean
  busy: boolean
  drafting: boolean
  onChange: (rule: RuleForm) => void
  onDraft: () => void
}) {
  const type = CRITERION_TYPES.find((option) => option.value === rule.criterionType)
  const set = (patch: Partial<RuleForm>) => onChange({ ...rule, ...patch })
  return (
    <div className="mt-1 mb-2 ml-4 space-y-2.5 rounded-lg border border-dashed bg-muted/30 p-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-muted-foreground">평가 기준 · 지원자에게 보이지 않아요</span>
        <label className="flex items-center gap-1.5 text-sm">
          <Checkbox
            aria-label={`${name} 중요`}
            checked={rule.important}
            onCheckedChange={(checked) => set({ important: checked === true })}
            disabled={locked}
          />
          중요
        </label>
        {!locked && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-6 px-2 text-xs"
            onClick={onDraft}
            disabled={busy}
          >
            <Sparkles className="size-3" />
            {drafting ? 'AI 작성 중…' : 'AI 초안'}
          </Button>
        )}
      </div>
      {duty && (
        <p className="text-xs text-muted-foreground">
          AI가 &apos;중요&apos;로 추천했어요 · 근거: 주요 업무 &apos;{duty}&apos;
        </p>
      )}
      {stale && (
        <p className="text-xs text-amber-700">
          기준을 정한 뒤 문장이 바뀌었어요. 기준이 지금 문장에 맞는지 확인해 주세요.
        </p>
      )}
      <div className="space-y-1">
        <div
          role="radiogroup"
          aria-label={`${name} 유형`}
          className="inline-flex rounded-lg border bg-background p-0.5 text-xs"
        >
          {CRITERION_TYPES.map((option) => (
            <button
              key={option.value}
              type="button"
              role="radio"
              aria-checked={rule.criterionType === option.value}
              disabled={locked}
              onClick={() => set({ criterionType: option.value })}
              className={cn(
                'rounded-md px-2.5 py-1',
                rule.criterionType === option.value
                  ? 'bg-foreground font-semibold text-background'
                  : 'text-muted-foreground',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        {type && <p className="text-xs text-muted-foreground">{type.hint}</p>}
      </div>
      <RuleField
        label="충족"
        name={name}
        value={rule.met}
        placeholder="이런 내용이 서류에서 확인되면 충족이에요"
        problem={problems.met}
        locked={locked}
        onChange={(met) => set({ met })}
      />
      {rule.criterionType === 'COMPOSITE' && (
        <RuleField
          label="부분 충족"
          name={name}
          value={rule.partial}
          placeholder="일부만 확인되면 부분 충족이에요"
          problem={problems.partial}
          locked={locked}
          onChange={(partial) => set({ partial })}
        />
      )}
      <RuleField
        label="미충족"
        name={name}
        value={rule.unmet}
        placeholder="확인되지 않으면 미충족이에요"
        problem={problems.unmet}
        locked={locked}
        onChange={(unmet) => set({ unmet })}
      />
      <label className="grid grid-cols-[72px_1fr] items-center gap-2">
        <span className="text-xs text-muted-foreground">인정 자격증</span>
        <Input
          aria-label={`${name} 인정 자격증`}
          value={rule.certificates}
          placeholder="자격증 조건일 때만, 쉼표로 나눠 써 주세요 (예: 정보처리기사)"
          disabled={locked}
          onChange={(event) => set({ certificates: event.target.value })}
          className="h-8 bg-background"
        />
      </label>
      {problems.certificates && <p className="text-xs text-destructive">{problems.certificates}</p>}
    </div>
  )
}

function RuleField({
  label,
  name,
  value,
  placeholder,
  problem,
  locked,
  onChange,
}: {
  label: string
  name: string
  value: string
  placeholder: string
  problem?: string
  locked: boolean
  onChange: (value: string) => void
}) {
  return (
    <label className="grid grid-cols-[72px_1fr] items-start gap-2">
      <span className="pt-1.5 text-xs text-muted-foreground">{label}</span>
      <div className="space-y-1">
        <Textarea
          aria-label={`${name} ${label} 기준`}
          rows={2}
          value={value}
          placeholder={placeholder}
          disabled={locked}
          aria-invalid={Boolean(problem)}
          onChange={(event) => onChange(event.target.value)}
          className="min-h-0 bg-background"
        />
        {problem && <p className="text-xs text-destructive">{problem}</p>}
      </div>
    </label>
  )
}

/** 서류 평가 칸. 선발 인원과 평가 기준 AI 초안. 지원자에게는 보이지 않는다 */
export function ScreeningBox({
  hireCount,
  onHireCount,
  hireProblem,
  filled,
  total,
  locked,
  busy,
  progress,
  stub,
  onFillAll,
}: {
  hireCount: string
  onHireCount: (value: string) => void
  hireProblem: string | null
  filled: number
  total: number
  locked: boolean
  busy: boolean
  progress: { done: number; total: number } | null
  stub: boolean | null
  onFillAll: () => void
}) {
  const { hash } = useLocation()

  // 게시 확인창의 [평가 기준 입력]으로 오면 이 칸을 보여 준다
  useEffect(() => {
    if (hash === `#${SCREENING_ID}`) {
      document.getElementById(SCREENING_ID)?.scrollIntoView({ block: 'start' })
    }
  }, [hash])

  return (
    <section
      id={SCREENING_ID}
      className="space-y-3 rounded-xl border border-dashed bg-muted/30 p-4"
    >
      <h2 className="flex flex-wrap items-center gap-1.5 text-sm font-bold">
        서류 평가
        {locked && <Lock className="size-3.5 text-muted-foreground" />}
        <span className="text-xs font-normal text-muted-foreground">
          지원자에게 보이지 않아요 · 평가 기준 {filled} / {total}개
        </span>
        {!locked && (
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            onClick={onFillAll}
            disabled={busy || total === 0}
          >
            <Sparkles />
            {progress ? `AI 초안 작성 중 ${progress.done}/${progress.total}` : '평가 기준 AI 초안'}
          </Button>
        )}
      </h2>
      <div className="space-y-1 text-xs text-muted-foreground">
        <p>
          자격 요건 · 우대 사항 줄마다 평가 기준을 펼쳐 정해요. 서류 평가 AI가 이 기준으로 지원서를
          판정해요. 기준이 없는 항목은 공고 문장 그대로 충족 · 미충족만 판정해요.
        </p>
        <p>
          &apos;중요&apos; 항목은 점수에 1.5배로 반영돼요.{' '}
          {locked
            ? '게시한 뒤에는 모든 지원자를 같은 기준으로 평가하려고 바꿀 수 없어요.'
            : 'AI 초안은 기준이 비어 있는 줄만 채우고, 저장해야 기준이 돼요.'}
        </p>
        {stub !== null && (
          <p className="flex items-center gap-1.5">
            <AgentChip name="Posting Agent" stub={stub} />이 쓴 초안이에요. 저장하기 전에 확인하고
            고쳐 주세요.
          </p>
        )}
      </div>
      <label className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-semibold">선발 인원</span>
        <Input
          type="number"
          min={1}
          max={1000}
          aria-label="선발 인원"
          value={hireCount}
          disabled={locked}
          onChange={(event) => onHireCount(event.target.value)}
          className="h-8 w-24 bg-background"
        />
        <span className="text-xs text-muted-foreground">
          명 · 서류 전형에서 이 인원의 10배수까지 AI가 추천해요
        </span>
      </label>
      {hireProblem && <p className="text-xs text-destructive">{hireProblem}</p>}
    </section>
  )
}
