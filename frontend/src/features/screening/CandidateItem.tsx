import { ArrowUp, Minus, Plus } from 'lucide-react'
import type { ReactNode } from 'react'

import { Checkbox } from '@/components/ui/checkbox'
import { careerLabel, type CandidateRow } from '@/features/screening/api'
import { cn } from '@/lib/utils'

/**
 * 선택 지원자 한 줄 (COM-02 표시 규칙). AI 선택은 보라 테두리, HR 결정은 배경색, 서류 기준은 굵기와 회색이다.
 * 서류 전형에서는 선 위(필수 조건 충족) 지원자가 굵게 보이고, 점수는 보여 주지 않는다.
 * 행을 누르면 지원자 카드가 열리므로 넣기 · 빼기는 오른쪽 버튼으로 한다.
 */
export function CandidateItem({
  row,
  documentStage,
  scoreStage,
  bordered,
  active,
  checkbox,
  action,
  note,
  onOpen,
}: {
  row: CandidateRow
  documentStage: boolean
  /** 평가 전형이면 오른쪽에 총점을, 결과가 없으면 "결과 없음"을 붙인다 */
  scoreStage?: boolean
  /** 선택 지원자 카드처럼 테두리가 기본으로 있는 모양 */
  bordered?: boolean
  active?: boolean
  checkbox?: { checked: boolean; onChange: (value: boolean) => void }
  action?: ReactNode
  /** 경력 아래 한 줄 (면접 전형의 면접관 의견 배지 등) */
  note?: ReactNode
  onOpen: () => void
}) {
  const gray = documentStage && !row.aboveLine
  return (
    // 행 어디를 눌러도 카드가 열린다. 키보드는 이름 버튼으로 연다
    <div
      onClick={onOpen}
      className={cn(
        'flex cursor-pointer items-center gap-3 rounded-lg border px-3 py-2 transition-all has-[button:focus-visible]:ring-2 has-[button:focus-visible]:ring-ring/50',
        bordered ? 'border-border' : 'border-transparent hover:bg-muted/60',
        row.decision === 'PASS' && 'bg-pass hover:bg-pass',
        row.decision === 'FAIL' && 'bg-fail hover:bg-fail',
        row.aiSelected &&
          '-translate-y-px border-ai shadow-[0_3px_10px_-4px_var(--ai)] ring-1 ring-ai/30',
        active && !row.aiSelected && 'border-foreground/30',
      )}
    >
      {checkbox && (
        <Checkbox
          aria-label={`${row.name} 체크`}
          checked={checkbox.checked}
          onClick={(event) => event.stopPropagation()}
          onCheckedChange={(value) => checkbox.onChange(value === true)}
        />
      )}
      <div className="min-w-0 flex-1">
        <div
          className={cn(
            'truncate text-sm',
            gray ? 'text-muted-foreground' : documentStage ? 'font-bold' : 'font-semibold',
          )}
        >
          {row.name}
        </div>
        <div className={cn('truncate text-xs text-muted-foreground', gray && 'opacity-80')}>
          {careerLabel(row)}
        </div>
        {note}
      </div>
      {scoreStage &&
        (row.score !== null ? (
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs font-bold tabular-nums">
            {Number(row.score)}
          </span>
        ) : (
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
            결과 없음
          </span>
        ))}
      {action}
    </div>
  )
}

export function RowButton({
  kind,
  label,
  disabled,
  onClick,
}: {
  kind: 'add' | 'remove' | 'up'
  label: string
  disabled?: boolean
  onClick: () => void
}) {
  const Icon = kind === 'add' ? Plus : kind === 'remove' ? Minus : ArrowUp
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
      className="flex size-7 shrink-0 items-center justify-center rounded-md border bg-background text-muted-foreground hover:text-foreground disabled:opacity-40"
    >
      <Icon className="size-3.5" />
    </button>
  )
}
