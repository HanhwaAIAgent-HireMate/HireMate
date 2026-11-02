import { Lock } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import {
  RECOMMENDATION_LABELS,
  RECOMMENDATION_STYLES,
  useMyOpinions,
  useSaveOpinion,
  type OpinionView,
  type Recommendation,
} from '@/features/interview/opinions'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const ROLE_LABELS = { HR: '인사', PRACTICAL: '실무' } as const

/**
 * 면접관 모드의 의견 카드: 내 추천도와 이유, 다른 면접관 의견. 다른 면접관 의견은 내 의견을 저장해야 열린다.
 * 결정은 채용 담당자가 하고, 의견은 AI에 넘기지 않는다.
 */
export function OpinionCard({
  stageId,
  applicationId,
  editable,
}: {
  stageId: string
  applicationId: string
  /** 진행 중인 전형 (결과를 확정하면 읽기만) */
  editable: boolean
}) {
  const opinions = useMyOpinions(stageId, applicationId)
  const mine = opinions.data?.find((opinion) => opinion.mine)
  const others = (opinions.data ?? []).filter((opinion) => !opinion.mine)
  if (!opinions.data || !mine) return null
  return (
    <section
      id="opinion"
      aria-label="면접관 의견"
      className="grid gap-3 rounded-xl border p-3 md:grid-cols-2"
    >
      <MyOpinion
        key={mine.updatedAt ?? 'new'}
        stageId={stageId}
        applicationId={applicationId}
        mine={mine}
        editable={editable}
      />
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">다른 면접관 의견</h3>
        {others.map((opinion) => (
          <OtherOpinion key={opinion.memberId} opinion={opinion} />
        ))}
      </div>
    </section>
  )
}

function MyOpinion({
  stageId,
  applicationId,
  mine,
  editable,
}: {
  stageId: string
  applicationId: string
  mine: OpinionView
  editable: boolean
}) {
  const save = useSaveOpinion(stageId, applicationId)
  const [recommendation, setRecommendation] = useState<Recommendation | null>(
    mine.recommendation ?? null,
  )
  const [comment, setComment] = useState(mine.comment ?? '')
  const changed =
    recommendation !== (mine.recommendation ?? null) || comment !== (mine.comment ?? '')
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold">내 의견 · {ROLE_LABELS[mine.role]}</h3>
      <div role="radiogroup" aria-label="추천도" className="flex gap-1.5">
        {(Object.keys(RECOMMENDATION_LABELS) as Recommendation[]).map((value) => (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={recommendation === value}
            disabled={!editable}
            onClick={() => setRecommendation(value)}
            className={cn(
              'rounded-lg border px-3 py-1 text-xs font-semibold',
              recommendation === value ? RECOMMENDATION_STYLES[value] : 'text-muted-foreground',
            )}
          >
            {RECOMMENDATION_LABELS[value]}
          </button>
        ))}
      </div>
      <Textarea
        aria-label="의견 이유"
        value={comment}
        rows={3}
        disabled={!editable}
        placeholder="판단한 이유를 적어 주세요. 나이 · 성별 · 출신 지역 · 혼인 여부 · 신체 조건은 쓰지 않아요."
        onChange={(event) => setComment(event.target.value)}
      />
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        {mine.updatedAt
          ? `${formatDateTime(mine.updatedAt)} 저장`
          : '결과 확정 전까지 고칠 수 있어요'}
        {editable && (
          <Button
            size="sm"
            className="ml-auto"
            disabled={!recommendation || !comment.trim() || !changed || save.isPending}
            onClick={() =>
              recommendation &&
              save.mutate(
                { recommendation, comment },
                {
                  onSuccess: () => toast.success('의견을 저장했어요.'),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            의견 저장
          </Button>
        )}
      </div>
    </div>
  )
}

function OtherOpinion({ opinion }: { opinion: OpinionView }) {
  const who = `${ROLE_LABELS[opinion.role]}${opinion.name ? ` · ${opinion.name}` : ''}`
  if (!opinion.submitted)
    return (
      <p className="rounded-lg border border-dashed p-2.5 text-xs text-muted-foreground">
        {who} — 아직 없음
      </p>
    )
  if (!opinion.recommendation)
    return (
      <p className="flex items-center gap-1.5 rounded-lg border border-dashed p-2.5 text-xs text-muted-foreground">
        <Lock className="size-3.5" />
        <b className="text-foreground">{who} — 제출함</b> 내 의견을 저장하면 내용이 보여요.
      </p>
    )
  return <OpinionLine opinion={opinion} />
}

/** 의견 한 줄 (HR 카드와 면접관 화면이 같이 쓴다) */
export function OpinionLine({
  opinion,
  scrollable = false,
}: {
  opinion: OpinionView
  scrollable?: boolean
}) {
  const who = `${ROLE_LABELS[opinion.role]}${opinion.name ? ` · ${opinion.name}` : ''}`
  if (!opinion.submitted || !opinion.recommendation)
    return (
      <p className="rounded-lg border border-dashed p-2.5 text-xs text-muted-foreground">
        {who} — 아직 없음
      </p>
    )
  return (
    <div className="min-w-0 space-y-1 rounded-lg border p-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span
          className={cn(
            'rounded-md border px-1.5 py-0.5 font-semibold',
            RECOMMENDATION_STYLES[opinion.recommendation],
          )}
        >
          {RECOMMENDATION_LABELS[opinion.recommendation]}
        </span>
        <b>{who}</b>
        {opinion.unassigned && <span className="text-muted-foreground">배정 해제됨</span>}
        {opinion.edited && opinion.updatedAt && (
          <span className="ml-auto text-muted-foreground">
            수정됨 · {formatDateTime(opinion.updatedAt)}
          </span>
        )}
      </div>
      <p
        className={cn(
          'break-words whitespace-pre-wrap text-muted-foreground',
          scrollable &&
            'max-h-48 overflow-y-auto overscroll-contain rounded-sm focus-visible:ring-2',
        )}
        role={scrollable ? 'region' : undefined}
        aria-label={scrollable ? `${who} 의견 내용` : undefined}
        tabIndex={scrollable ? 0 : undefined}
      >
        {opinion.comment}
      </p>
    </div>
  )
}
