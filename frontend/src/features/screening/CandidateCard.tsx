import { ArrowLeft, ChevronDown, NotebookPen, RotateCw } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { ApplicantAvatar } from '@/components/ApplicantAvatar'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import {
  careerLabel,
  useCandidateDetail,
  useSchoolMentionActions,
  useRetryAnalysis,
  useSaveMemo,
  type StageOverview,
} from '@/features/screening/api'
import { AssessmentViewer } from '@/features/assessment/AssessmentViewer'
import { scheduleLabel, useInterview } from '@/features/interview/api'
import { InterviewViewer } from '@/features/interview/InterviewViewer'
import { CandidateInterviewProgress } from '@/features/interview/CandidateInterviewProgress'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'
import { AdminRequestButton } from '@/components/AdminRequestButton'
import { toastAiError } from '@/lib/admin-request'

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
  const { checked, toggleChecked, open, tableOpen } = useStageUi()

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <button
          onClick={() => open(null)}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          {tableOpen ? '표 보기' : `선택 지원자 ${selectedCount}`}
        </button>
        {detail.data && (
          <MemoButton
            stageId={overview.stageId}
            applicationId={applicationId}
            memo={detail.data.memo}
            interview={overview.type === 'INTERVIEW'}
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
              {/* 이름 옆 원형 사진 (예시 사진). 블라인드 · 성별을 모르는 이름은 아이콘 */}
              <ApplicantAvatar applicationId={applicationId} name={detail.data.row.name} />
              {overview.type === 'INTERVIEW' ? (
                <div>
                  <h3 className="text-lg font-bold">{detail.data.row.name}</h3>
                  <p className="text-xs text-muted-foreground">
                    <InterviewSubtitle
                      stageId={overview.stageId}
                      applicationId={applicationId}
                      fallback={careerLabel(detail.data.row)}
                    />
                  </p>
                </div>
              ) : (
                // 경력 · 이전 직무는 이름 오른쪽에 둔다
                <div className="flex min-w-0 items-baseline gap-2">
                  <h3 className="shrink-0 text-lg font-bold">{detail.data.row.name}</h3>
                  <p className="truncate text-xs text-muted-foreground">
                    {careerLabel(detail.data.row)}
                  </p>
                </div>
              )}
            </div>
            {overview.type === 'INTERVIEW' && (
              <CandidateInterviewProgress
                stageId={overview.stageId}
                applicationId={applicationId}
              />
            )}
            {detail.data.row.analysisStatus === 'FAILED' && (
              <RetryAnalysis
                stageId={overview.stageId}
                recruitmentId={overview.recruitmentId}
                applicationId={applicationId}
              />
            )}
            {overview.type === 'DOCUMENT' && detail.data.schoolMentions.length > 0 && (
              <SchoolMentions
                stageId={overview.stageId}
                applicationId={applicationId}
                mentions={detail.data.schoolMentions}
                cleared={detail.data.schoolCleared}
                editable={editable}
              />
            )}
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

/** AI 분석에 실패한 지원자. 담당자가 다시 분석을 요청하면 분석 중으로 바뀌고 끝나는 대로 결과가 반영된다 */
function RetryAnalysis({
  stageId,
  recruitmentId,
  applicationId,
}: {
  stageId: string
  recruitmentId: string
  applicationId: string
}) {
  const retry = useRetryAnalysis(stageId, recruitmentId, applicationId)
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
      <span>AI 분석에 실패했어요. 다시 분석하면 끝나는 대로 결과가 반영돼요.</span>
      <AdminRequestButton />
      <Button
        size="sm"
        variant="outline"
        disabled={retry.isPending}
        onClick={() =>
          retry.mutate(undefined, {
            onSuccess: () => toast.success('다시 분석을 요청했어요.'),
            onError: toastAiError,
          })
        }
      >
        <RotateCw />
        다시 분석
      </Button>
    </div>
  )
}

/**
 * 서류 전형의 블라인드 위반 의심. 출신 학교를 쓴 문장을 학교 이름을 가린 채 접어 두고, HR이 확인해 해제하면 리스트의
 * 원래 자리로 돌아간다. 잘못 해제했으면 해제 취소로 되돌린다. 해제는 결정이나 감점이 아니다 (아키텍처 규칙 1)
 */
function SchoolMentions({
  stageId,
  applicationId,
  mentions,
  cleared,
  editable,
}: {
  stageId: string
  applicationId: string
  mentions: string[]
  cleared: boolean
  editable: boolean
}) {
  const [open, setOpen] = useState(false)
  const { clear, undo } = useSchoolMentionActions(stageId, applicationId)
  const action = cleared ? undo : clear
  return (
    <div
      className={cn(
        'rounded-md border px-2 py-1 text-xs',
        cleared ? 'bg-muted/40' : 'border-amber-200 bg-amber-50',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className={cn(
            'inline-flex items-center gap-1',
            cleared ? 'text-muted-foreground' : 'font-semibold',
          )}
        >
          <ChevronDown className={cn('size-3.5 transition-transform', !open && '-rotate-90')} />
          {cleared
            ? '블라인드 위반 의심을 해제했어요'
            : `블라인드 위반 의심 문장 ${mentions.length}개`}
        </button>
        {editable && (
          <Button
            size="xs"
            variant="outline"
            disabled={action.isPending}
            onClick={() =>
              action.mutate(undefined, {
                onSuccess: () =>
                  toast.success(
                    cleared
                      ? '해제를 취소했어요. 블라인드 위반 의심으로 다시 옮겼어요.'
                      : '블라인드 위반 의심을 해제했어요.',
                  ),
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            {cleared ? '해제 취소' : '해제'}
          </Button>
        )}
      </div>
      {open && (
        <div className="mt-1 space-y-1">
          <ul className="space-y-0.5">
            {mentions.map((mention) => (
              <li key={mention}>· {mention}</li>
            ))}
          </ul>
          <p className="text-[11px] text-muted-foreground">
            학교 이름은 가려져 있어요. 출신 학교가 아니면 해제하세요. 반영할지는 담당자가 정해요.
          </p>
        </div>
      )}
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
  interview,
}: {
  stageId: string
  applicationId: string
  memo: string
  interview: boolean
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
        <h4 className="text-sm font-semibold">채용 담당자 공용 메모</h4>
        <Textarea
          aria-label="메모"
          rows={5}
          value={text}
          placeholder="이 지원자에 대한 메모를 남겨요. 지원자에게는 보이지 않아요."
          onChange={(event) => setText(event.target.value)}
        />
        {interview && (
          <p className="text-xs text-muted-foreground">
            질문에 참고하려면 AI Chat에 ‘메모를 참고해 질문을 만들어 주세요’라고 요청해 주세요.
          </p>
        )}
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
