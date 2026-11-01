import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { useHeaderCrumb } from '@/app/header-store'
import { Button } from '@/components/ui/button'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { Textarea } from '@/components/ui/textarea'
import { InterviewerScript } from '@/features/interview/InterviewerScript'
import { Results } from '@/features/interview/InterviewViewer'
import { RoleTag } from '@/features/interview/RoleTag'
import {
  useMyInterviews,
  useWorkspace,
  useWorkspaceActions,
  type AssignedInterview,
  type InterviewerWorkspace,
} from '@/features/interview/sessions'
import { useCandidateDetail } from '@/features/screening/api'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

/**
 * 면접관 모드의 면접 진행 화면. 왼쪽은 이 전형에서 내가 배정된 지원자(면접 시간순), 가운데는 질문 대본(내 담당 질문에만
 * 기록)과 개인 메모, 오른쪽은 지원 자료 · 전형 결과. 결정 · 선택 · 마감 기능은 없다.
 */
export function InterviewRoomPage() {
  const { stageId = '' } = useParams()
  const [params, setParams] = useSearchParams()
  const interviews = useMyInterviews()
  const rows = (interviews.data?.items ?? []).filter((item) => item.stageId === stageId)
  const selected = rows.find((row) => row.applicationId === params.get('candidate')) ?? rows[0]
  useHeaderCrumb(selected && { title: `${selected.recruitmentTitle} › ${selected.stageName}` })

  return (
    <div className="flex h-full flex-col">
      <h1 className="sr-only">면접 진행</h1>
      <ResizablePanelGroup id="interview-room" className="min-h-0 flex-1">
        <ResizablePanel
          id="room-candidates"
          defaultSize={240}
          minSize={200}
          groupResizeBehavior="preserve-pixel-size"
          className="flex flex-col"
        >
          <CandidateColumn
            rows={rows}
            selected={selected?.applicationId ?? null}
            onSelect={(applicationId) => setParams({ candidate: applicationId })}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="room-main" minSize={480} className="flex flex-col">
          {selected ? (
            <Room key={selected.applicationId} interview={selected} />
          ) : (
            <p className="p-6 text-sm text-muted-foreground">
              {interviews.isPending ? '면접을 불러오고 있어요.' : '이 전형에 배정된 면접이 없어요.'}
            </p>
          )}
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}

const STATUS_LABELS: Record<AssignedInterview['status'], string> = {
  SCHEDULED: '예정',
  IN_PROGRESS: '진행 중',
  ENDED: '끝남',
}

/** 왼쪽 칸: 오늘 면접(시간순), 다른 날, 일정 미정 */
function CandidateColumn({
  rows,
  selected,
  onSelect,
}: {
  rows: AssignedInterview[]
  selected: string | null
  onSelect: (applicationId: string) => void
}) {
  const today = new Date().toDateString()
  const at = (row: AssignedInterview) => row.schedule?.scheduledAt ?? null
  const sorted = [...rows].sort((a, b) => (at(a) ?? '9999').localeCompare(at(b) ?? '9999'))
  const groups: [string, AssignedInterview[]][] = [
    [
      '오늘 면접',
      sorted.filter((row) => at(row) && new Date(at(row) ?? '').toDateString() === today),
    ],
    [
      '다른 날',
      sorted.filter((row) => at(row) && new Date(at(row) ?? '').toDateString() !== today),
    ],
    ['일정 미정', sorted.filter((row) => !at(row))],
  ]
  return (
    <nav aria-label="면접 지원자" className="min-h-0 flex-1 overflow-auto bg-surface px-2.5 py-3">
      {groups
        .filter(([, items]) => items.length > 0)
        .map(([label, items]) => (
          <section key={label} className="mb-4">
            <h2 className="mb-1.5 px-1.5 text-xs font-semibold text-muted-foreground">
              {label} · {items.length}명
            </h2>
            {items.map((row) => (
              <button
                key={row.applicationId}
                type="button"
                aria-current={row.applicationId === selected ? 'true' : undefined}
                onClick={() => onSelect(row.applicationId)}
                className={cn(
                  'mb-1 block w-full rounded-lg px-2.5 py-2 text-left text-sm',
                  row.applicationId === selected
                    ? 'bg-background shadow-sm'
                    : 'hover:bg-background/60',
                )}
              >
                <span className="flex items-center justify-between gap-2">
                  <b>{row.applicantName}</b>
                  <span
                    className={cn(
                      'rounded-full px-1.5 py-0.5 text-[11px] font-semibold',
                      row.status === 'IN_PROGRESS'
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-muted text-muted-foreground',
                    )}
                  >
                    {STATUS_LABELS[row.status]}
                  </span>
                </span>
                <span className="text-xs text-muted-foreground">
                  {at(row) ? formatDateTime(at(row) ?? '') : '일정 미정'}
                </span>
              </button>
            ))}
          </section>
        ))}
    </nav>
  )
}

type SideTab = 'documents' | 'results'

/** 가운데 · 오른쪽: 지원자 한 명의 면접. 위쪽에 진행 상태와 [면접 시작] · [면접 종료] */
function Room({ interview }: { interview: AssignedInterview }) {
  const { stageId, applicationId } = interview
  const workspace = useWorkspace(stageId, applicationId)
  const actions = useWorkspaceActions(stageId, applicationId)
  const [filter, setFilter] = useState<'all' | 'mine'>('all')
  const [side, setSide] = useState<SideTab>('documents')
  const fail = (error: unknown) => toast.error(errorMessage(error))
  const data = workspace.data
  const mine = (data?.questions ?? []).filter(
    (item) => item.question.interviewerRole === data?.myRole,
  )
  const recorded = mine.filter((item) => item.question.answer.trim()).length
  const status = data?.session.status

  return (
    <ResizablePanelGroup id="interview-room-work" className="min-h-0 flex-1">
      <ResizablePanel id="room-script" minSize={420} className="flex flex-col">
        <div className="flex items-center gap-3 border-b px-5 py-3">
          <div className="min-w-0">
            <h2 className="flex items-center gap-2 truncate text-lg font-bold">
              {interview.applicantName}
              <RoleTag
                role={interview.myRole}
                questionText={`${interview.applicantName} 내 담당`}
              />
            </h2>
            <p className="text-xs text-muted-foreground">
              {data?.schedule?.scheduledAt
                ? formatDateTime(data.schedule.scheduledAt)
                : '일정 미정'}
            </p>
          </div>
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span>
              내 질문 {recorded}/{mine.length} 기록
            </span>
            {status && status !== 'IN_PROGRESS' && (
              <Button
                size="sm"
                disabled={actions.start.isPending || status === 'ENDED'}
                onClick={() => actions.start.mutate(undefined, { onError: fail })}
              >
                {status === 'ENDED' ? '면접 끝남' : '면접 시작'}
              </Button>
            )}
            {status === 'IN_PROGRESS' && (
              <Button
                size="sm"
                variant="outline"
                disabled={actions.end.isPending}
                onClick={() => actions.end.mutate(undefined, { onError: fail })}
              >
                면접 종료
              </Button>
            )}
          </div>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-auto px-5 py-4">
          <div className="flex justify-end">
            <div
              role="group"
              aria-label="질문 보기"
              className="flex overflow-hidden rounded-lg border text-xs"
            >
              {(
                [
                  ['all', '모든 질문'],
                  ['mine', '내 질문만'],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  aria-pressed={filter === key}
                  onClick={() => setFilter(key)}
                  className={cn(
                    'px-2.5 py-1',
                    filter === key ? 'bg-muted font-semibold' : 'text-muted-foreground',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          {!data ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <>
              {status === 'SCHEDULED' && (
                <p className="rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
                  [면접 시작]을 누르면 답변을 기록할 수 있어요. 시작 전에는 질문만 미리 볼 수
                  있어요.
                </p>
              )}
              <InterviewerScript
                stageId={stageId}
                applicationId={applicationId}
                workspace={data}
                filter={filter}
                ownerNames={{}}
              />
              <PersonalMemo
                key={data.session.version}
                stageId={stageId}
                applicationId={applicationId}
                workspace={data}
              />
            </>
          )}
        </div>
      </ResizablePanel>
      <ResizableHandle withHandle />
      <ResizablePanel
        id="room-side"
        defaultSize={380}
        minSize={300}
        groupResizeBehavior="preserve-pixel-size"
        className="flex flex-col border-l"
      >
        <div role="tablist" className="flex gap-5 border-b px-4 pt-3 text-sm">
          {(
            [
              ['documents', '지원 자료'],
              ['results', '전형 결과'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              role="tab"
              aria-selected={side === key}
              onClick={() => setSide(key)}
              className={cn(
                '-mb-px border-b-2 pb-2',
                side === key
                  ? 'border-foreground font-semibold'
                  : 'border-transparent text-muted-foreground',
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 overflow-auto p-4">
          {side === 'results' ? (
            <Results stageId={stageId} applicationId={applicationId} />
          ) : (
            <Documents
              stageId={stageId}
              applicationId={applicationId}
              recruitmentId={interview.recruitmentId}
            />
          )}
        </div>
      </ResizablePanel>
    </ResizablePanelGroup>
  )
}

function Documents({
  stageId,
  applicationId,
  recruitmentId,
}: {
  stageId: string
  applicationId: string
  recruitmentId: string
}) {
  const detail = useCandidateDetail(stageId, applicationId)
  if (detail.isError)
    return <p className="text-sm text-muted-foreground">지원 자료를 열 수 없어요.</p>
  if (!detail.data) return <Skeleton className="h-40 w-full" />
  return <DocumentViewer stageId={stageId} recruitmentId={recruitmentId} detail={detail.data} />
}

/** 나만 보는 면접 메모. 다른 면접관과 HR에게는 보이지 않는다 */
function PersonalMemo({
  stageId,
  applicationId,
  workspace,
}: {
  stageId: string
  applicationId: string
  workspace: InterviewerWorkspace
}) {
  const actions = useWorkspaceActions(stageId, applicationId)
  const [text, setText] = useState(workspace.personalMemo)
  const changed = text !== workspace.personalMemo
  return (
    <section className="space-y-2 rounded-xl border p-3">
      <h3 className="text-sm font-semibold">내 메모</h3>
      <Textarea
        aria-label="내 메모"
        value={text}
        rows={3}
        placeholder="나만 보는 메모예요. 다른 면접관과 채용 담당자에게는 보이지 않아요."
        onChange={(event) => setText(event.target.value)}
      />
      <div className="flex justify-end">
        <Button
          size="sm"
          variant="outline"
          disabled={!changed || actions.memo.isPending}
          onClick={() =>
            actions.memo.mutate(
              { text, expectedVersion: workspace.session.version },
              {
                onSuccess: () => toast.success('메모를 저장했어요.'),
                onError: (error) => toast.error(errorMessage(error)),
              },
            )
          }
        >
          메모 저장
        </Button>
      </div>
    </section>
  )
}
