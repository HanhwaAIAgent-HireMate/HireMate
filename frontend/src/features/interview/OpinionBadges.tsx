import { RECOMMENDATION_LABELS, type CandidateOpinions } from '@/features/interview/opinions'
import { cn } from '@/lib/utils'

const ROLE_LABELS = { HR: '인사', PRACTICAL: '실무' } as const

/**
 * HR 지원자 목록의 면접관 의견 배지: 인사 추천 · 실무 미제출. 면접이 종료된 지원자에게만 붙인다 (CandidateList).
 * 면접관이 배정되지 않은 지원자는 아무것도 없다
 */
export function OpinionBadges({ row }: { row: CandidateOpinions | undefined }) {
  const opinions = (row?.opinions ?? []).filter((opinion) => !opinion.unassigned)
  if (opinions.length === 0) return null
  return (
    <div className="mt-0.5 flex gap-1 text-[11px]" aria-label="면접관 의견">
      {opinions.map((opinion) => (
        <span
          key={opinion.memberId}
          className={cn(
            'rounded px-1 font-semibold',
            opinion.recommendation === 'RECOMMEND' && 'bg-pass text-pass-foreground',
            opinion.recommendation === 'HOLD' && 'bg-amber-50 text-amber-800',
            opinion.recommendation === 'NOT_RECOMMEND' && 'bg-fail text-fail-foreground',
            !opinion.recommendation && 'bg-muted text-muted-foreground',
          )}
        >
          {ROLE_LABELS[opinion.role]}{' '}
          {opinion.recommendation ? RECOMMENDATION_LABELS[opinion.recommendation] : '미제출'}
        </span>
      ))}
    </div>
  )
}
