import { Bot, Download, FileChartColumn, Link2, Loader2 } from 'lucide-react'
import { useParams } from 'react-router'
import { toast } from 'sonner'

import { useHeaderCrumb } from '@/app/header-store'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePosting } from '@/features/posting/api'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import {
  toReportView,
  useAgentReport,
  useFinalReports,
  useOpenFinalReport,
} from '@/features/report/api'
import { ReportBody, ReportTitle } from '@/features/report/ReportBody'
import { ReportProgress } from '@/features/report/ReportProgress'
import { errorMessage } from '@/lib/api/client'
import { formatShortDateTime } from '@/lib/format'

// RPT-01 최종 채용 리포트. 채용 종료 때 Report Agent가 모든 전형을 그래프로 정리하는 문서이며 채용 상태를 바꾸지 않는다
export function ReportPage() {
  const { recruitmentId = '' } = useParams()
  const posting = usePosting(recruitmentId)
  const finals = useFinalReports(recruitmentId, posting.data?.status === 'CLOSED')
  useHeaderCrumb(
    posting.data && {
      title: posting.data.content.title,
      status: RECRUITMENT_STATUS_LABELS[posting.data.status],
      careersPath: careersPath(posting.data.postingId),
    },
  )

  const latest = finals.data?.[0]
  if (latest) {
    return (
      <FinalReport recruitmentId={recruitmentId} stageId={latest.stageId} reportId={latest.id} />
    )
  }
  const closed = posting.data?.status === 'CLOSED'
  return (
    <NoFinalReport
      recruitmentId={recruitmentId}
      closed={closed}
      loading={posting.isLoading || (closed && finals.isLoading)}
    />
  )
}

/** 최종 리포트가 아직 없는 채용. 종료한 채용이면 새로 만들 수 있다 */
function NoFinalReport({
  recruitmentId,
  closed,
  loading,
}: {
  recruitmentId: string
  closed: boolean
  loading: boolean
}) {
  const create = useOpenFinalReport(recruitmentId)
  return (
    <div className="mx-auto max-w-[1040px] space-y-3 p-6">
      <h1 className="text-lg font-bold">채용 리포트</h1>
      {loading ? (
        <Skeleton className="h-60 w-full" />
      ) : closed ? (
        <div className="space-y-3">
          <p className="text-sm text-muted-foreground">
            아직 최종 리포트가 없어요. 만들면 Report Agent가 모든 전형을 그래프로 정리해요.
          </p>
          <Button
            variant="outline"
            size="sm"
            className="border-ai/30 text-ai hover:bg-ai-soft hover:text-ai"
            disabled={create.isPending}
            onClick={() =>
              create.mutate(undefined, { onError: (error) => toast.error(errorMessage(error)) })
            }
          >
            <FileChartColumn />
            그래프 리포트 만들기
          </Button>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          리포트가 아직 없어요. 마지막 전형을 마치고 채용을 종료하면 만들어져요.
        </p>
      )}
    </div>
  )
}

/** Report Agent가 모든 전형을 부품 설계서로 정리한 최종 리포트 */
function FinalReport({
  recruitmentId,
  stageId,
  reportId,
}: {
  recruitmentId: string
  stageId: string
  reportId: string
}) {
  const report = useAgentReport(stageId, reportId)
  const reopen = useOpenFinalReport(recruitmentId)
  const view = report.data ? toReportView(report.data) : null

  if (!view) {
    const failed = report.isError || report.data?.status === 'FAILED'
    return (
      <div className="mx-auto max-w-[1040px] space-y-3 p-6">
        <h1 className="text-lg font-bold">채용 리포트</h1>
        {failed ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              최종 리포트를 만들지 못했어요. 리포트는 채용 상태를 바꾸지 않아요.
            </p>
            <Button
              variant="outline"
              size="sm"
              disabled={reopen.isPending}
              onClick={() =>
                reopen.mutate(undefined, { onError: (error) => toast.error(errorMessage(error)) })
              }
            >
              다시 만들기
            </Button>
          </div>
        ) : (
          <>
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              Report Agent가 모든 전형 기록을 살펴 최종 리포트를 쓰고 있어요.
            </p>
            <ReportProgress
              createdAt={report.data?.createdAt}
              expectedSeconds={report.data?.expectedSeconds}
            />
            <Skeleton className="h-60 w-full" />
          </>
        )}
      </div>
    )
  }

  return (
    <article className="mx-auto max-w-[1100px] space-y-5 p-6 print:p-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-md bg-ai-soft px-2 py-0.5 text-xs font-medium text-ai">
          <Bot className="size-3" />
          Report Agent
        </span>
        <span className="text-xs text-muted-foreground">
          {formatShortDateTime(view.bundle.asOf)} 기준 · 채용 종료 시 작성
        </span>
        {view.skills.map((skill) => (
          <span
            key={skill}
            className="rounded-md bg-ai-soft px-2 py-0.5 text-[11.5px] font-semibold text-ai"
          >
            스킬 · {skill}
          </span>
        ))}
        {view.fallback && (
          <span className="rounded-md bg-fail px-2 py-0.5 text-[11.5px] font-semibold text-fail-foreground">
            기본 구성
          </span>
        )}
        <ReportActions />
      </div>
      <h1 className="text-xl font-bold">
        최종 채용 리포트 — <ReportTitle report={view} />
      </h1>
      <div className="rounded-2xl bg-muted/40 p-5">
        <ReportBody report={view} />
      </div>
    </article>
  )
}

function ReportActions() {
  const copy = async () => {
    await navigator.clipboard.writeText(window.location.href)
    toast.success('리포트 링크를 복사했어요. 로그인한 담당자만 열 수 있어요.')
  }
  return (
    <div className="ml-auto flex gap-2 print:hidden">
      <Button variant="outline" size="sm" onClick={() => window.print()}>
        <Download />
        PDF
      </Button>
      <Button variant="outline" size="sm" onClick={() => void copy()}>
        <Link2 />
        링크 복사
      </Button>
    </div>
  )
}
