import { ChevronRight } from 'lucide-react'
import { Link } from 'react-router'

import { Skeleton } from '@/components/ui/skeleton'
import { RoleTag } from '@/features/interview/RoleTag'
import {
  INTERVIEW_STATUS_LABELS,
  useMyInterviews,
  type AssignedInterview,
} from '@/features/interview/sessions'
import { formatDateTime } from '@/lib/format'

/** 면접관 모드의 첫 화면: 내가 배정된 면접 전형. 면접관은 전형에 배정되므로 전형 하나를 카드 하나로 두고, 지원자는 들어가서 넘겨 본다 */
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
          아직 배정된 면접이 없어요. 채용 담당자가 면접 전형에 면접관을 지정하면 그 전형이 여기에
          보여요.
        </p>
      ) : (
        <div className="grid max-w-5xl gap-4 lg:grid-cols-2">
          {[...groups.values()].map((items) => (
            <StageCard key={items[0].stageId} items={items} />
          ))}
        </div>
      )}
    </div>
  )
}

/** 면접 전형 하나. 누르면 그 전형의 면접 진행 화면으로 들어간다 */
function StageCard({ items }: { items: AssignedInterview[] }) {
  const first = items[0]
  const count = (status: AssignedInterview['status']) =>
    items.filter((item) => item.status === status).length
  // 다음 면접: 아직 시작하지 않은 면접 중 가장 이른 일정
  const next = items
    .filter((item) => item.status === 'SCHEDULED' && item.schedule?.scheduledAt)
    .map((item) => item.schedule?.scheduledAt ?? '')
    .sort()[0]

  return (
    <Link
      to={`/interviewer/stages/${first.stageId}`}
      className="group flex items-center gap-4 rounded-xl border bg-background p-4 transition-colors hover:border-foreground/30"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs text-muted-foreground">{first.recruitmentTitle}</p>
        <h2 className="mt-0.5 flex items-center gap-2 text-base font-bold">
          {first.stageName}
          <RoleTag role={first.myRole} questionText={`${first.stageName} 내`} />
        </h2>
        <p className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
          <span>
            지원자 <b className="text-foreground">{items.length}</b>명
          </span>
          {(['IN_PROGRESS', 'SCHEDULED', 'ENDED'] as const)
            .filter((status) => count(status) > 0)
            .map((status) => (
              <span key={status}>
                {INTERVIEW_STATUS_LABELS[status]} <b className="text-foreground">{count(status)}</b>
              </span>
            ))}
          {next && <span>다음 면접 {formatDateTime(next)}</span>}
        </p>
      </div>
      <ChevronRight className="size-5 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
    </Link>
  )
}
