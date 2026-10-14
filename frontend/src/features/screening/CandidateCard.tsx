import { ArrowLeft, NotebookPen } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  careerLabel,
  useCandidateDetail,
  useSaveMemo,
  type StageOverview,
} from '@/features/screening/api'
import { AssessmentViewer } from '@/features/assessment/AssessmentViewer'
import { scheduleLabel, useInterview } from '@/features/interview/api'
import { InterviewViewer } from '@/features/interview/InterviewViewer'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'
import { formatMonthDay } from '@/lib/format'

/** 가운데 영역의 지원자 카드. 전형 종류에 맞는 Viewer를 보여 주고, 결정은 위쪽 체크박스와 맨 아래 버튼으로 한다. */
export function CandidateCard({
  overview,
  applicationId,
  editable,
  selectedCount,
}: {
  overview: StageOverview
  applicationId: string
  editable: boolean
  selectedCount: number
}) {
  const detail = useCandidateDetail(overview.stageId, applicationId)
  const { checked, toggleChecked, open } = useStageUi()

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <button
          onClick={() => open(null)}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          선택 지원자 {selectedCount}
        </button>
        {detail.data && (
          <MemoButton
            stageId={overview.stageId}
            applicationId={applicationId}
            memo={detail.data.memo}
          />
        )}
      </div>
      <div className="min-h-0 flex-1 overflow-auto px-4 pb-4">
        {!detail.data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              {editable && detail.data.row.decision === 'PENDING' && (
                <Checkbox
                  aria-label={`${detail.data.row.name} 체크`}
                  checked={checked.includes(applicationId)}
                  onCheckedChange={(value) => toggleChecked(applicationId, value === true)}
                />
              )}
              <div>
                <h3 className="text-lg font-bold">{detail.data.row.name}</h3>
                <p className="text-xs text-muted-foreground">
                  {overview.type === 'INTERVIEW' ? (
                    <InterviewSubtitle
                      stageId={overview.stageId}
                      applicationId={applicationId}
                      fallback={careerLabel(detail.data.row)}
                    />
                  ) : (
                    `${careerLabel(detail.data.row)} · 지원 ${formatMonthDay(detail.data.submittedAt)}`
                  )}
                </p>
              </div>
            </div>
            {overview.type === 'INTERVIEW' ? (
              <InterviewViewer
                stageId={overview.stageId}
                recruitmentId={overview.recruitmentId}
                detail={detail.data}
                editable={editable}
              />
            ) : overview.type === 'ASSESSMENT' ? (
              <AssessmentViewer
                stageId={overview.stageId}
                recruitmentId={overview.recruitmentId}
                detail={detail.data}
              />
            ) : (
              <DocumentViewer
                stageId={overview.stageId}
                recruitmentId={overview.recruitmentId}
                detail={detail.data}
              />
            )}
          </div>
        )}
      </div>
    </div>
  )
}

/** 면접 전형은 이름 아래에 면접 일정을 보여 준다. 일정이 없으면 경력을 보여 준다. */
function InterviewSubtitle({
  stageId,
  applicationId,
  fallback,
}: {
  stageId: string
  applicationId: string
  fallback: string
}) {
  const interview = useInterview(stageId, applicationId)
  return <>{scheduleLabel(interview.data?.schedule ?? null) || `${fallback} · 면접 일정 미정`}</>
}

function MemoButton({
  stageId,
  applicationId,
  memo,
}: {
  stageId: string
  applicationId: string
  memo: string
}) {
  const save = useSaveMemo(stageId, applicationId)
  const [text, setText] = useState(memo)
  const [openState, setOpenState] = useState(false)
  return (
    <Popover
      open={openState}
      onOpenChange={(value) => {
        setOpenState(value)
        if (value) setText(memo)
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="sm">
          <NotebookPen />
          메모{memo && ' ·'}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-2">
        <Textarea
          aria-label="메모"
          rows={5}
          value={text}
          placeholder="이 지원자에 대한 메모를 남겨요. 지원자에게는 보이지 않아요."
          onChange={(event) => setText(event.target.value)}
        />
        <div className="flex justify-end">
          <Button
            size="sm"
            disabled={save.isPending}
            onClick={() =>
              save.mutate(text, {
                onSuccess: () => {
                  toast.success('메모를 저장했어요.')
                  setOpenState(false)
                },
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            저장
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  )
}
