import { Loader2 } from 'lucide-react'

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { errorMessage } from '@/lib/api/client'

import { toReportView, useAgentReport } from './api'
import { ReportModal } from './ReportModal'
import { ReportProgress } from './ReportProgress'

/**
 * 리포트 ID로 여는 모달. Report Agent가 쓰는 동안은 진행 화면을 보여 주고, 다 쓰면 리포트를 그린다.
 * 선택 지원자의 [리포트 생성]과 Chat 리포트 카드가 같이 쓴다.
 */
export function AgentReportModal({
  stageId,
  reportId,
  onClose,
}: {
  stageId: string
  reportId: string | null
  onClose: () => void
}) {
  const report = useAgentReport(stageId, reportId)
  const view = report.data ? toReportView(report.data) : null
  const open = reportId !== null
  const onOpenChange = (next: boolean) => !next && onClose()

  if (view) return <ReportModal report={view} open={open} onOpenChange={onOpenChange} />

  const failed = report.isError || report.data?.status === 'FAILED'
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex flex-col gap-4 sm:max-w-lg">
        <DialogTitle className="text-base font-bold">
          {failed ? '리포트를 만들지 못했어요' : 'Report Agent가 리포트를 쓰고 있어요'}
        </DialogTitle>
        <DialogDescription asChild>
          <div className="flex flex-col gap-3 text-sm text-muted-foreground">
            {failed ? (
              <p>
                {report.isError
                  ? errorMessage(report.error)
                  : '잠시 뒤 다시 요청해 주세요. 리포트는 채용 상태를 바꾸지 않아요.'}
              </p>
            ) : (
              <>
                <p className="flex items-center gap-2">
                  <Loader2 className="size-4 animate-spin" />
                  스킬을 읽고 전형 기록을 살펴 그래프와 근거를 고르는 중이에요.
                </p>
                <ReportProgress
                  createdAt={report.data?.createdAt}
                  expectedSeconds={report.data?.expectedSeconds}
                />
                <Skeleton className="h-32 w-full" />
              </>
            )}
          </div>
        </DialogDescription>
      </DialogContent>
    </Dialog>
  )
}
