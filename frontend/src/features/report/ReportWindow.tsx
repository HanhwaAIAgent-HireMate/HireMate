import { cn } from 'cn'
import { Loader2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/api/client'
import { formatShortDateTime } from '@/lib/format'

import { toReportView, useAgentReport, useRequestCompareReport } from './api'
import { DistributionView } from './DistributionView'
import { ReportBody, ReportTitle } from './ReportBody'
import { ReportProgress } from './ReportProgress'

export type ReportTab = 'deep' | 'distribution'

const TABS: { value: ReportTab; label: string }[] = [
  { value: 'deep', label: '심층 분석' },
  { value: 'distribution', label: '분포' },
]

/**
 * 서류 전형 리포트 창. 오른쪽 위 버튼으로 심층 분석(체크한 2~5명 비교 리포트)과 분포(전형 전체)를 바꿔 본다.
 * 분포의 경계 그룹에서 [심층 분석]을 누르면 그 사람들로 비교 리포트를 요청하고 심층 분석으로 넘어간다.
 * 여는 쪽이 key를 바꿔 열 때마다 처음 상태로 돌아간다.
 */
export function ReportWindow({
  stageId,
  initialTab,
  initialReportId,
  onClose,
}: {
  stageId: string
  initialTab: ReportTab
  initialReportId: string | null
  onClose: () => void
}) {
  const [tab, setTab] = useState<ReportTab>(initialTab)
  const [reportId, setReportId] = useState<string | null>(initialReportId)
  const request = useRequestCompareReport(stageId)
  const deepDive = (applicationIds: string[]) =>
    request.mutate(
      { applicationIds, focus: '', brief: false },
      {
        onSuccess: (requested) => {
          setReportId(requested.reportId)
          setTab('deep')
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="flex max-h-[90vh] w-full flex-col gap-0 overflow-hidden bg-background p-0 sm:max-w-5xl">
        <header className="flex items-center justify-between gap-4 border-b bg-background px-6 pt-5 pb-4">
          <div className="flex min-w-0 flex-col gap-1">
            <span className="text-xs font-bold text-ai">◇ Report Agent</span>
            <DialogTitle className="text-xl font-bold">서류 전형 리포트</DialogTitle>
            <DialogDescription className="text-xs">
              {tab === 'deep'
                ? '경계에 있는 몇 명을 근거와 함께 비교해요.'
                : '전형 지원자 전원의 판정을 코드가 센 그대로 보여 줘요.'}
            </DialogDescription>
          </div>
          <div role="tablist" className="mr-8 flex shrink-0 rounded-lg bg-muted p-[3px]">
            {TABS.map((option) => (
              <button
                key={option.value}
                role="tab"
                aria-selected={tab === option.value}
                onClick={() => setTab(option.value)}
                className={cn(
                  'rounded-md px-3 py-1 text-sm font-medium',
                  tab === option.value
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </header>
        <div className="overflow-y-auto bg-muted/40 px-6 py-5">
          {tab === 'distribution' ? (
            <DistributionView
              stageId={stageId}
              onDeepDive={deepDive}
              deepPending={request.isPending}
            />
          ) : (
            <DeepReport stageId={stageId} reportId={reportId} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 심층 분석. 비교 리포트를 쓰는 동안은 진행 막대를, 다 쓰면 리포트를 그린다 */
function DeepReport({ stageId, reportId }: { stageId: string; reportId: string | null }) {
  const report = useAgentReport(stageId, reportId)
  if (reportId === null) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        분포의 경계 그룹에서 [심층 분석]을 누르거나, 선택 지원자 2~5명을 체크하고 [리포트 생성]을
        누르면 여기에 나와요.
      </p>
    )
  }
  const view = report.data ? toReportView(report.data) : null
  if (view) {
    return (
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">
            {formatShortDateTime(view.bundle.asOf)} 기준
          </span>
          <h3 className="text-lg font-bold">
            <ReportTitle report={view} />
          </h3>
          <div className="flex flex-wrap gap-1">
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
          </div>
        </div>
        <ReportBody report={view} />
      </div>
    )
  }
  if (report.isError || report.data?.status === 'FAILED') {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        {report.isError
          ? errorMessage(report.error)
          : '리포트를 만들지 못했어요. 잠시 뒤 다시 요청해 주세요.'}
      </p>
    )
  }
  return (
    <div className="flex flex-col gap-3 text-sm text-muted-foreground">
      <p className="flex items-center gap-2">
        <Loader2 className="size-4 animate-spin" />
        스킬을 읽고 지원자 기록을 살펴 근거를 고르는 중이에요. 그동안 분포를 먼저 볼 수 있어요.
      </p>
      <ReportProgress
        createdAt={report.data?.createdAt}
        expectedSeconds={report.data?.expectedSeconds}
      />
      <Skeleton className="h-32 w-full" />
    </div>
  )
}
