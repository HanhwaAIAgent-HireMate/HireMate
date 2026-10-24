import { useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { useCandidateProfile } from '@/features/screening/api'
import {
  VERIFICATIONS,
  agentLabel,
  categoryLabel,
  countByVerification,
  filterByVerification,
  verificationLabel,
  type Verification,
  type VerificationFilter,
} from '@/features/screening/profile'
import { cn } from '@/lib/utils'

/** 확인 상태 배지 색. 색만으로 구분하지 않도록 이름을 함께 쓴다 */
const BADGE: Record<Verification, string> = {
  CONFIRMED: 'bg-pass text-pass-foreground',
  EVIDENCED: 'bg-ai-soft text-ai',
  UNCONFIRMED: 'bg-amber-50 text-amber-800',
  CONFLICT: 'bg-fail text-fail-foreground',
}

const CHIPS: { key: VerificationFilter; label: string }[] = [
  { key: 'ALL', label: '전체' },
  ...VERIFICATIONS,
]

/**
 * 지원자 카드의 프로필 탭 (STG-06). 분석 Agent(지원서 · 평가 · 면접)가 쌓은 항목을 확인 상태와 함께 보여 주고,
 * 칩으로 확인 상태를 골라 본다. 확인된 사실과 AI 해석을 구분해 보여 주기 위해서다 (NFR-03)
 */
export function ProfilePanel({
  stageId,
  applicationId,
}: {
  stageId: string
  applicationId: string
}) {
  const [filter, setFilter] = useState<VerificationFilter>('ALL')
  const profile = useCandidateProfile(stageId, applicationId)

  if (profile.isPending) return <Skeleton className="h-24 w-full" />
  if (profile.isError) return <p className="text-muted-foreground">프로필을 불러오지 못했어요.</p>
  const { status, items } = profile.data
  if (status === null || items.length === 0) {
    return (
      <p className="text-muted-foreground">
        아직 프로필이 없어요. AI 분석이 끝나면 항목이 여기에 쌓여요.
      </p>
    )
  }
  const counts = countByVerification(items)
  const shown = filterByVerification(items, filter)

  return (
    <div className="space-y-3">
      <div role="group" aria-label="확인 상태로 보기" className="flex flex-wrap gap-1.5">
        {CHIPS.map((chip) => (
          <button
            key={chip.key}
            type="button"
            aria-pressed={filter === chip.key}
            onClick={() => setFilter(chip.key)}
            className={cn(
              'rounded-full border px-2.5 py-1 text-xs',
              filter === chip.key
                ? 'border-foreground bg-foreground text-background'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {chip.label} <span className="font-semibold tabular-nums">{counts[chip.key]}</span>
          </button>
        ))}
      </div>
      {shown.length === 0 ? (
        <p className="text-muted-foreground">이 확인 상태의 항목이 없어요.</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((item, index) => (
            <li key={`${index}-${item.content}`} className="space-y-1 rounded-lg border p-3">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium">
                  {categoryLabel(item.category)}
                </span>
                <span className="font-medium">{item.content}</span>
                <span
                  className={cn(
                    'ml-auto rounded-full px-2 py-0.5 text-xs font-semibold',
                    BADGE[item.verification],
                  )}
                >
                  {verificationLabel(item.verification)}
                </span>
              </div>
              {item.evidence ? (
                <p className="text-xs">“{item.evidence}”</p>
              ) : (
                <p className="text-xs text-muted-foreground">근거 문장 없음</p>
              )}
              <p className="text-xs text-muted-foreground">
                출처 {item.source} · {agentLabel(item.agent)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
