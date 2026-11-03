import { Download } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { formatShortDateTime } from '@/lib/format'

import { ReportBody, ReportTitle } from './ReportBody'
import type { ReportView } from './types'

/** 리포트 모달. 미리보기를 먼저 보여 주고, PDF는 위쪽 작은 버튼으로 받는다 */
export function ReportModal({
  report,
  open,
  onOpenChange,
}: {
  report: ReportView | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[90vh] w-full flex-col gap-0 overflow-hidden bg-background p-0 sm:max-w-5xl">
        {report && (
          <>
            <header className="flex items-start justify-between gap-4 border-b bg-background px-6 pt-5 pb-4">
              <div className="flex min-w-0 flex-col gap-1.5">
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="font-bold text-ai">◇ Report Agent</span>
                  {report.bundle.brief && (
                    <span className="rounded bg-muted px-1.5 py-0.5 font-semibold">간략히</span>
                  )}
                  <span>{formatShortDateTime(report.bundle.asOf)} 기준</span>
                  {report.bundle.focus && <span>· 관점 {report.bundle.focus}</span>}
                </div>
                <DialogTitle className="text-xl font-bold">
                  <ReportTitle report={report} />
                </DialogTitle>
                <DialogDescription asChild>
                  <div className="flex flex-wrap gap-1">
                    {report.skills.map((skill) => (
                      <span
                        key={skill}
                        className="rounded-md bg-ai-soft px-2 py-0.5 text-[11.5px] font-semibold text-ai"
                      >
                        스킬 · {skill}
                      </span>
                    ))}
                    {report.fallback && (
                      <span className="rounded-md bg-fail px-2 py-0.5 text-[11.5px] font-semibold text-fail-foreground">
                        기본 구성
                      </span>
                    )}
                  </div>
                </DialogDescription>
              </div>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    className="mr-8 shrink-0"
                    aria-label="PDF 다운로드"
                    onClick={() =>
                      toast.info(
                        'PDF는 출력 워커를 연결하면 받을 수 있어요. 지금은 미리보기만 돼요.',
                      )
                    }
                  >
                    <Download />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>PDF 다운로드</TooltipContent>
              </Tooltip>
            </header>
            <div className="overflow-y-auto bg-muted/40 px-6 py-5">
              <ReportBody report={report} />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
