import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { RoleTag } from '@/features/interview/RoleTag'
import { useMyInterviews, type AssignedInterview } from '@/features/interview/sessions'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const STATUS_LABELS: Record<AssignedInterview['status'], string> = {
  SCHEDULED: '예정',
  IN_PROGRESS: '진행 중',
  ENDED: '끝남',
}

/** 면접관 모드의 첫 화면: 내가 배정된 면접. 채용 · 전형별로 묶고 면접 시간순으로 둔다 */
export function MyInterviewsPage() {
  const interviews = useMyInterviews()
  const groups = new Map<string, AssignedInterview[]>()
  for (const item of interviews.data?.items ?? []) {
    groups.set(item.stageId, [...(groups.get(item.stageId) ?? []), item])
  }

  return (
    <div className="min-h-full bg-surface px-6 py-6">
      <h1 className="mb-4 text-lg font-bold">내 면접</h1>
      {interviews.isPending ? (
        <Skeleton className="h-28 w-full max-w-xl" />
      ) : groups.size === 0 ? (
        <p className="max-w-xl rounded-xl border border-dashed bg-background p-6 text-sm text-muted-foreground">
          아직 배정된 면접이 없어요. 채용 담당자가 면접 전형에 면접관을 지정하면 해당 전형의
          지원자들이 여기에 보여요.
        </p>
      ) : (
        <div className="grid max-w-5xl gap-4 lg:grid-cols-2">
          {[...groups.values()].map((items) => (
            <StageGroup key={items[0].stageId} items={items} />
          ))}
        </div>
      )}
    </div>
  )
}

function StageGroup({ items }: { items: AssignedInterview[] }) {
  const sorted = [...items].sort((a, b) =>
    (a.schedule?.scheduledAt ?? '9999').localeCompare(b.schedule?.scheduledAt ?? '9999'),
  )
  const first = sorted[0]
  return (
    <section
      aria-label={`${first.recruitmentTitle} ${first.stageName}`}
      className="rounded-xl border bg-background p-4"
    >
      <p className="truncate text-xs text-muted-foreground">{first.recruitmentTitle}</p>
      <h2 className="mt-0.5 mb-3 text-base font-bold">{first.stageName}</h2>
      <ul className="divide-y">
        {sorted.map((item) => (
          <li key={item.applicationId}>
            <Link
              to={`/interviewer/stages/${item.stageId}?candidate=${item.applicationId}`}
              className="flex items-center gap-2 py-2 text-sm hover:bg-muted/40"
            >
              <RoleTag role={item.myRole} questionText={`${item.applicantName} 내 담당`} />
              <b>{item.applicantName}</b>
              <span className="text-xs text-muted-foreground">
                {item.schedule?.scheduledAt
                  ? formatDateTime(item.schedule.scheduledAt)
                  : '일정 미정'}
              </span>
              <span
                className={cn(
                  'ml-auto rounded-full px-2 py-0.5 text-[11px] font-semibold',
                  item.status === 'IN_PROGRESS'
                    ? 'bg-amber-100 text-amber-800'
                    : 'bg-muted text-muted-foreground',
                )}
              >
                {STATUS_LABELS[item.status]}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  )
}
