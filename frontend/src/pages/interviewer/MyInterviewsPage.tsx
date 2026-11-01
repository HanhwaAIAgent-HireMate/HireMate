import { Skeleton } from '@/components/ui/skeleton'
import { useMyInterviews, type AssignedStage } from '@/features/interview/assignments'
import { RoleTag } from '@/features/interview/RoleTag'
import { cn } from '@/lib/utils'

const STATUS_LABELS: Record<AssignedStage['status'], string> = {
  PENDING: '시작 전',
  ACTIVE: '진행 중',
  CONFIRMED: '결과 확정 · 읽기만',
  DONE: '종료 · 읽기만',
}

/** 면접관 모드의 첫 화면: 내가 지정된 면접 전형 */
export function MyInterviewsPage() {
  const stages = useMyInterviews()

  return (
    <div className="min-h-full bg-surface px-6 py-6">
      <h1 className="mb-4 text-lg font-bold">내 면접</h1>
      {stages.isPending ? (
        <Skeleton className="h-28 w-full max-w-sm" />
      ) : !stages.data?.length ? (
        <p className="max-w-xl rounded-xl border border-dashed bg-background p-6 text-sm text-muted-foreground">
          아직 지정된 면접이 없어요. 채용 담당자가 면접 전형에 면접관으로 지정하면 여기에 보여요.
        </p>
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {stages.data.map((stage) => (
            <li key={stage.stageId}>
              <StageCard stage={stage} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function StageCard({ stage }: { stage: AssignedStage }) {
  const closed = stage.status === 'CONFIRMED' || stage.status === 'DONE'
  return (
    <article
      className={cn('h-full rounded-xl border bg-background p-4', closed && 'opacity-60')}
      aria-label={`${stage.recruitmentTitle} ${stage.stageName}`}
    >
      <p className="truncate text-xs text-muted-foreground">{stage.recruitmentTitle}</p>
      <h2 className="mt-0.5 mb-2 text-base font-bold">{stage.stageName}</h2>
      <div className="flex flex-wrap gap-1.5">
        {stage.roles.map((role) => (
          <RoleTag key={role} role={role} questionText={`${stage.stageName} 내 담당`} />
        ))}
      </div>
      <div className="mt-3 flex gap-3 text-xs text-muted-foreground">
        <span>
          지원자 <b className="text-foreground">{stage.candidateCount}</b>명
        </span>
        <span>{STATUS_LABELS[stage.status]}</span>
      </div>
    </article>
  )
}
