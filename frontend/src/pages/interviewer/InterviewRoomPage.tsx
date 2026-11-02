import { useState } from 'react'
import { useParams, useSearchParams } from 'react-router'

import { useHeaderCrumb } from '@/app/header-store'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Skeleton } from '@/components/ui/skeleton'
import { ChatPanel } from '@/features/chat/ChatPanel'
import { InterviewerScript } from '@/features/interview/InterviewerScript'
import { NoteEditor } from '@/features/interview/NoteEditor'
import { SharedNotes } from '@/features/interview/SharedNotes'
import { OpinionCard } from '@/features/interview/OpinionCard'
import { Results } from '@/features/interview/InterviewViewer'
import { InterviewSessionBar } from '@/features/interview/InterviewSessionBar'
import {
  useEnterInterview,
  useInterviewAttendance,
  useInterviewRoomLive,
} from '@/features/interview/live'
import { usePendingAnswerSaves } from '@/features/interview/pending-saves'
import {
  INTERVIEW_STATUS_LABELS,
  useInterviewerTab,
  useMyInterviews,
  useWorkspace,
  useWorkspaceActions,
  type AssignedInterview,
  type InterviewerWorkspace,
} from '@/features/interview/sessions'
import { useCandidateDetail } from '@/features/screening/api'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
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
  const groups = candidateGroups(rows)
  // 전형으로 들어오면 지원자를 고르지 않았으니 왼쪽 목록 맨 위 지원자를 연다
  const selected =
    rows.find((row) => row.applicationId === params.get('candidate')) ??
    groups.flatMap(([, items]) => items)[0]
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
            groups={groups}
            selected={selected?.applicationId ?? null}
            onSelect={(applicationId) => setParams({ candidate: applicationId })}
          />
        </ResizablePanel>
        <ResizableHandle withHandle />
        <ResizablePanel id="room-main" minSize={480} className="flex flex-col">
          {selected ? (
            <Room key={selected.applicationId} interview={selected} assigned={rows} />
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

const scheduledAt = (row: AssignedInterview) => row.schedule?.scheduledAt ?? null

/** 왼쪽 칸의 묶음: 오늘 면접, 다른 날, 일정 미정. 묶음 안은 면접 시간순이고 빈 묶음은 뺀다 */
function candidateGroups(rows: AssignedInterview[]): [string, AssignedInterview[]][] {
  const today = new Date().toDateString()
  const sorted = [...rows].sort((a, b) =>
    (scheduledAt(a) ?? '9999').localeCompare(scheduledAt(b) ?? '9999'),
  )
  const day = (row: AssignedInterview) => new Date(scheduledAt(row) ?? '').toDateString()
  const groups: [string, AssignedInterview[]][] = [
    ['오늘 면접', sorted.filter((row) => scheduledAt(row) && day(row) === today)],
    ['다른 날', sorted.filter((row) => scheduledAt(row) && day(row) !== today)],
    ['일정 미정', sorted.filter((row) => !scheduledAt(row))],
  ]
  return groups.filter(([, items]) => items.length > 0)
}

/** 왼쪽 칸: 오늘 면접(시간순), 다른 날, 일정 미정 */
function CandidateColumn({
  groups,
  selected,
  onSelect,
}: {
  groups: [string, AssignedInterview[]][]
  selected: string | null
  onSelect: (applicationId: string) => void
}) {
  const at = scheduledAt
  return (
    <nav aria-label="면접 지원자" className="min-h-0 flex-1 overflow-auto bg-surface px-2.5 py-3">
      {groups.map(([label, items]) => (
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
                  {INTERVIEW_STATUS_LABELS[row.status]}
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

type SideTab = 'chat' | 'documents' | 'results'

/** 면접관 Chat의 예시 질문. 선택 지원자는 바꿀 수 없어 찾기 대신 분석 · 질문 예시를 둔다 */
const CHAT_EXAMPLES = [
  '이 지원자가 프로젝트에서 본인이 한 일을 정리해줘',
  '본인 역할을 확인할 질문 하나 더 만들어줘',
]

/** 가운데 · 오른쪽: 지원자 한 명의 면접. 위쪽에 진행 상태와 [면접 시작] · [면접 종료] */
function Room({
  interview,
  assigned,
}: {
  interview: AssignedInterview
  assigned: AssignedInterview[]
}) {
  const { stageId, applicationId } = interview
  const tab = useInterviewerTab(stageId)
  const workspace = useWorkspace(stageId, applicationId)
  const actions = useWorkspaceActions(stageId, applicationId)
  const [filter, setFilter] = useState<'all' | 'mine'>('all')
  const [side, setSide] = useState<SideTab>('chat')
  const attendance = useInterviewAttendance(stageId, applicationId)
  const enter = useEnterInterview(stageId, applicationId)
  const live = useInterviewRoomLive(stageId, applicationId)
  const saves = usePendingAnswerSaves()
  const [ending, setEnding] = useState(false)
  const data = workspace.data
  const status = data?.session.status
  const ownerNames = Object.fromEntries(
    (attendance.data?.attendees ?? []).map((attendee) => [attendee.role, attendee.name]),
  )
  async function endInterview() {
    setEnding(true)
    try {
      await saves.flush()
      await actions.end.mutateAsync()
    } finally {
      setEnding(false)
    }
  }

  return (
    <ResizablePanelGroup id="interview-room-work" className="min-h-0 flex-1">
      <ResizablePanel id="room-script" minSize={420} className="flex flex-col">
        <InterviewSessionBar
          interview={interview}
          workspace={data}
          attendance={attendance.data}
          connected={live.connected}
          entering={enter.isPending}
          busy={ending || actions.start.isPending}
          onEnter={() => enter.mutateAsync()}
          onStart={() => actions.start.mutateAsync()}
          onEnd={endInterview}
        />
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
              {data.previous.map((previous) => (
                <section
                  key={previous.stageId}
                  className="space-y-2 rounded-xl bg-muted/60 p-3 text-sm"
                >
                  <h3 className="font-semibold">{previous.stageName} 기록</h3>
                  {previous.questions.map((question) => (
                    <div key={question.questionId}>
                      <p className="font-medium">{question.text}</p>
                      <p className="whitespace-pre-wrap text-muted-foreground">
                        {question.answer || '기록 없음'}
                      </p>
                    </div>
                  ))}
                </section>
              ))}
              <InterviewerScript
                stageId={stageId}
                applicationId={applicationId}
                workspace={data}
                filter={filter}
                ownerNames={ownerNames}
                registerSave={saves.register}
                savingBeforeEnd={ending}
              />
              <OpinionCard
                stageId={stageId}
                applicationId={applicationId}
                editable={attendance.data?.stageActive === true}
              />
              <SharedNotes
                stageId={stageId}
                applicationId={applicationId}
                interviewer
                editable={
                  status === 'IN_PROGRESS' && !ending && attendance.data?.stageActive === true
                }
              />
              <PersonalMemo
                stageId={stageId}
                applicationId={applicationId}
                workspace={data}
                editable={
                  status === 'IN_PROGRESS' && attendance.data?.stageActive === true && !ending
                }
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
              ['chat', 'AI Chat'],
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
        {side === 'chat' ? (
          tab.data ? (
            <ChatPanel
              overview={{
                stageId,
                name: interview.stageName,
                type: 'INTERVIEW',
                counts: { total: assigned.length },
              }}
              tabId={tab.data.id}
              people={assigned.map((row) => ({
                applicationId: row.applicationId,
                name: row.applicantName,
              }))}
              examples={CHAT_EXAMPLES}
            />
          ) : (
            <p className="p-4 text-sm text-muted-foreground">
              {tab.isPending
                ? 'AI Chat을 여는 중이에요.'
                : '진행 중인 전형에서 AI Chat을 쓸 수 있어요.'}
            </p>
          )
        ) : (
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
        )}
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
  editable,
}: {
  stageId: string
  applicationId: string
  workspace: InterviewerWorkspace
  editable: boolean
}) {
  const actions = useWorkspaceActions(stageId, applicationId)
  const query = useWorkspace(stageId, applicationId)
  return (
    <NoteEditor
      stageId={stageId}
      applicationId={applicationId}
      field="personal-memo"
      label="내 메모"
      description="나만 보는 메모예요. 다른 면접관과 채용 담당자에게는 보이지 않아요."
      text={workspace.personalMemo}
      version={workspace.personalMemoVersion}
      editable={editable}
      reload={() => query.refetch({ throwOnError: true })}
      save={async (text, expectedVersion) => {
        const stored = await actions.memo.mutateAsync({ text, expectedVersion })
        return { text: stored.personalMemo, version: stored.personalMemoVersion }
      }}
    />
  )
}
