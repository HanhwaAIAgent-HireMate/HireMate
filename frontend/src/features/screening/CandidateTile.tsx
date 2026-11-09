import type { ReactNode } from 'react'

import { ApplicantIcon } from '@/components/ApplicantIcon'
import { careerYearsLabel, type CandidateRow } from '@/features/screening/api'
import { cn } from '@/lib/utils'

/**
 * 전체 지원자 카드 한 장 (기본 폭에서 한 줄에 3장). 이름과 그 아래 경력(경력 n년 · 신입)만 보여 준다.
 * 이름 앞에 지원자 아이콘을 둔다. 이름은 네 글자까지 잘리지 않게 글자를 조금 줄이고, 오른쪽 위 버튼 자리만 비운다.
 * 합격은 초록, 불합격은 빨강 배경이고, AI가 고른 지원자는 보라 테두리다.
 * 서류 전형에서 필수 조건을 못 채운 지원자(선 아래)는 회색이다. 카드를 누르면 지원자 카드가 열리고,
 * 넣기 · 빼기 · ↑는 오른쪽 위 버튼으로 한다. 평가 전형은 경력 옆에 평가 점수(외부 평가 결과)를 붙인다.
 */
export function CandidateTile({
  row,
  documentStage,
  scoreStage,
  active,
  action,
  note,
  suspect = false,
  onOpen,
}: {
  row: CandidateRow
  documentStage: boolean
  /** 블라인드 위반 의심. 노란 칸에 보통 글자색으로 보인다 (낮은 평가가 아니라 확인이 필요한 지원자다) */
  suspect?: boolean
  scoreStage: boolean
  active: boolean
  action: ReactNode
  /** 경력 아래 한 줄 (면접 전형의 면접 진행 · 면접관 의견 배지 등) */
  note?: ReactNode
  onOpen: () => void
}) {
  const gray = documentStage && !row.aboveLine && !suspect
  const missing = documentStage ? row.missingRequired.length : 0
  return (
    // 카드 어디를 눌러도 지원자 카드가 열린다. 키보드는 이름 버튼으로 연다
    <div
      onClick={onOpen}
      title={
        gray && missing > 0
          ? `필수 조건 ${missing}개를 충족하지 못했거나 확인이 필요해요`
          : undefined
      }
      className={cn(
        'relative flex min-w-0 cursor-pointer flex-col gap-0.5 rounded-lg border bg-background px-2.5 py-2 transition-all hover:border-foreground/30 has-[button:focus-visible]:ring-2 has-[button:focus-visible]:ring-ring/50',
        row.decision === 'PASS' && 'border-pass-foreground/30 bg-pass',
        row.decision === 'FAIL' && 'border-fail-foreground/30 bg-fail',
        gray && row.decision === 'PENDING' && 'border-dashed bg-muted/50',
        suspect && row.decision === 'PENDING' && 'border-amber-200 bg-amber-50',
        row.aiSelected && 'border-ai shadow-[0_3px_10px_-4px_var(--ai)] ring-1 ring-ai/30',
        active && !row.aiSelected && 'border-foreground/40',
      )}
    >
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation()
          onOpen()
        }}
        className={cn(
          'flex min-w-0 items-center gap-1 pr-5 text-left text-[13px] outline-none',
          gray ? 'text-muted-foreground' : 'font-bold',
        )}
      >
        <ApplicantIcon />
        <span className="truncate">{row.name}</span>
      </button>
      <span className={cn('truncate text-xs text-muted-foreground', gray && 'opacity-80')}>
        {careerYearsLabel(row)}
        {scoreStage && (
          <span className="ml-1 font-semibold text-foreground tabular-nums">
            {row.score !== null ? Number(row.score) : '결과 없음'}
          </span>
        )}
      </span>
      {note}
      {/* 버튼을 조금 작게 해 이름 자리를 넓힌다 */}
      {action && <div className="absolute top-1 right-1 [&_button]:size-6">{action}</div>}
    </div>
  )
}
