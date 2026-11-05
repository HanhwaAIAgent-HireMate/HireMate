import { LoaderCircle, Lock, Send } from 'lucide-react'
import { Fragment, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { useHeaderCrumb } from '@/app/header-store'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { VariableField } from '@/features/company/VariableField'
import { useInterviewScheduling } from '@/features/interview/scheduling'
import {
  needsDraft,
  noticeBadge,
  useEditNotice,
  useNoticeAiRequest,
  useNoticePreview,
  useNotices,
  usePrepareNotice,
  useSaveOnboarding,
  useSendNotice,
  type Notice,
  type OnboardingGuide,
} from '@/features/notice/api'
import { emptyFields, type GuideField } from '@/features/notice/guide'
import { GuideFields } from '@/features/notice/GuideFields'
import { MailFrame } from '@/features/notice/MailFrame'
import { sentenceDiff } from '@/features/notice/sentenceDiff'
import { NEXT_STAGE_GUIDE_ID } from '@/features/notice/StageGuides'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import { errorReply } from '@/features/posting/errorReply'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { useStageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '불합격 안내 말투를 조금 더 따뜻하게 바꿔줘',
  '내용을 짧게 줄여줘',
  '추가: 문의는 recruit@example.com으로 해 주세요.',
]

/** 입사 안내 칸. 입사일은 최종 합격자를 정한 뒤에 정해져, 공고가 아니라 최종 합격 안내를 보낼 때 이 화면에서 쓴다 */
const ONBOARDING_FIELDS: GuideField<keyof OnboardingGuide>[] = [
  { key: 'startDate', label: '입사일', placeholder: '예: 12월 1일(월) 오전 9시', maxLength: 200 },
  {
    key: 'place',
    label: '출근 장소',
    placeholder: '예: 서울 중구 OO빌딩 5층 인사팀',
    maxLength: 500,
  },
  {
    key: 'documents',
    label: '제출 서류',
    placeholder: '예: 졸업증명서, 경력증명서',
    maxLength: 1000,
  },
  { key: 'preparation', label: '준비 사항', placeholder: '예: 신분증', maxLength: 1000 },
  {
    key: 'note',
    label: '기타 안내',
    placeholder: '한 줄에 하나씩 써요. 예: 11월 25일까지 서류를 보내 주세요',
    maxLength: 1000,
    optional: true,
  },
]
const ONBOARDING_ID = 'onboarding'
/** 보낼 모습은 메일을 실제 폭으로 그린 뒤 줄여, 편집 화면 폭에 맞추고 스크롤을 줄인다 */
const PREVIEW_SCALE = 0.8
/** 다음 면접 안내의 일정 아래에 두는 메모. 미리보기의 메모와 같은 말이다 */
const INTERVIEW_TIME_HINT = '보낼 때 지원자마다 배정된 면접 시각이 함께 들어가요'
/** 입사 안내를 비워 두면 backend가 본문 아래에 붙이는 문장 */
const ONBOARDING_LATER = '입사 일정과 준비 사항은 담당자가 별도로 안내드릴 예정입니다.'

// MSG-01 안내 초안 확인 · 수정. 공고 작성과 같은 방식으로 고치고, HR이 확인한 뒤 직접 발송한다
export function NoticeEditorPage() {
  const { stageId = '', group = 'PASS' } = useParams()
  const overview = useStageOverview(stageId)
  const notices = useNotices(stageId)
  useHeaderCrumb(
    overview.data && {
      title: overview.data.recruitmentTitle,
      status: RECRUITMENT_STATUS_LABELS[overview.data.recruitmentStatus],
      careersPath: careersPath(overview.data.postingId),
    },
  )
  const notice = notices.data?.find((item) => item.group === group)
  // AI 초안은 이 화면에서 그룹마다 쓴다. 전형 종료 화면은 기다리지 않는다
  const drafting = Boolean(notice && needsDraft(notice))
  const prepare = usePrepareNotice(stageId, group === 'FAIL' ? 'FAIL' : 'PASS', drafting)
  if (!overview.data || !notice) {
    return (
      <div className="p-6">
        <h1 className="sr-only">안내 초안</h1>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }
  const closePath = `/hr/recruitments/${overview.data.recruitmentId}/stages/${stageId}/close`
  if (drafting && !prepare.isSuccess) {
    return (
      <Drafting
        notice={notice}
        stageName={overview.data.name}
        closePath={closePath}
        error={prepare.isError ? errorMessage(prepare.error) : null}
        onRetry={() => void prepare.refetch()}
      />
    )
  }
  return (
    <Editor
      key={`${notice.group}-${notice.content}`}
      notice={notice}
      notices={notices.data ?? []}
      stageName={overview.data.name}
      closePath={closePath}
      guidesPath={`${closePath}#${NEXT_STAGE_GUIDE_ID}`}
    />
  )
}

/** Communication Agent가 초안을 쓰는 동안 보여 준다. 다른 화면으로 가도 초안은 계속 쓴다 */
function Drafting({
  notice,
  stageName,
  closePath,
  error,
  onRetry,
}: {
  notice: Notice
  stageName: string
  closePath: string
  error: string | null
  onRetry: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-bold">{notice.label}</h1>
        <span className="text-xs text-muted-foreground">{stageName} 종료 · ② 합격·불합격 안내</span>
      </div>
      <div className="flex flex-1 items-center justify-center p-6">
        <div
          role="status"
          aria-live="polite"
          className="w-full max-w-sm space-y-3 rounded-xl border p-6 text-center"
        >
          {error ? (
            <>
              <p className="font-semibold">초안을 쓰지 못했어요</p>
              <p className="text-sm text-muted-foreground">{error}</p>
              <Button onClick={onRetry}>다시 쓰기</Button>
            </>
          ) : (
            <>
              <LoaderCircle className="mx-auto size-7 animate-spin text-ai" />
              <p className="font-semibold">AI가 {notice.label} 초안을 쓰고 있어요</p>
              <p className="text-sm text-muted-foreground">
                {notice.recipientCount}명에게 보낼 안내예요. 30초쯤 걸릴 수 있어요. 다 쓰면 바로
                고칠 수 있어요.
              </p>
            </>
          )}
          <Button variant="outline" size="sm" asChild>
            <Link to={closePath}>전형 종료 화면으로</Link>
          </Button>
        </div>
      </div>
    </div>
  )
}

function Editor({
  notice,
  notices,
  stageName,
  closePath,
  guidesPath,
}: {
  notice: Notice
  notices: Notice[]
  stageName: string
  closePath: string
  /** 전형 결과 화면의 다음 전형 안내 칸 */
  guidesPath: string
}) {
  const navigate = useNavigate()
  const [confirmingGuide, setConfirmingGuide] = useState(false)
  const [draft, setDraft] = useState({
    subject: notice.subject,
    greeting: notice.greeting,
    content: notice.content,
    closing: notice.closing,
  })
  const [onboarding, setOnboarding] = useState<OnboardingGuide>(notice.onboarding)
  const [proposal, setProposal] = useState<string | null>(null)
  const [messages, setMessages] = useState<AiMessage[]>([])
  const [view, setView] = useState<'edit' | 'preview'>('edit')
  const preview = useNoticePreview(notice.stageId, notice.group, view === 'preview')
  const edit = useEditNotice(notice.stageId, notice.group)
  const saveOnboarding = useSaveOnboarding(notice.stageId, notice.group)
  const send = useSendNotice(notice.stageId)
  // 다음 전형이 면접이면 면접 시간을 배정한 뒤에 합격 안내를 보낸다 (보내면 다음 전형 안내가 잠긴다)
  const scheduling = useInterviewScheduling(
    notice.stageId,
    notice.group === 'PASS' && notice.status === 'DRAFT',
  )
  const waitingSchedule =
    notice.group === 'PASS' &&
    notice.status === 'DRAFT' &&
    !(scheduling.data && ['READY', 'NOT_APPLICABLE'].includes(scheduling.data.status))
  const ai = useNoticeAiRequest(notice.stageId, notice.group)
  const editable = notice.status === 'DRAFT'
  const final = notice.templateType === 'FINAL_PASS'
  const textDirty =
    draft.subject !== notice.subject ||
    draft.greeting !== notice.greeting ||
    draft.content !== notice.content ||
    draft.closing !== notice.closing
  const onboardingDirty =
    final &&
    ONBOARDING_FIELDS.some((field) => onboarding[field.key] !== notice.onboarding[field.key])
  const dirty = textDirty || onboardingDirty

  const save = async () => {
    try {
      if (textDirty) await edit.mutateAsync(draft)
      if (onboardingDirty) await saveOnboarding.mutateAsync(onboarding)
      return true
    } catch (error) {
      toast.error(errorMessage(error))
      return false
    }
  }

  const request = async (message: string) => {
    setMessages((current) => [...current, { role: 'user', text: message }])
    if (!(await save())) return
    try {
      const answer = await ai.mutateAsync(message)
      setProposal(answer.content)
      setMessages((current) => [
        ...current,
        { role: 'ai', text: answer.reply, agent: answer.agent, stub: answer.stub },
      ])
    } catch (error) {
      setMessages((current) => [...current, errorReply(error)])
    }
  }

  // 보낼 모습은 저장한 초안으로 backend가 만든다. 고친 내용이 있으면 먼저 저장한다
  const changeView = async (next: string) => {
    if (next === 'preview' && editable && dirty && !(await save())) return
    setView(next === 'preview' ? 'preview' : 'edit')
  }

  const apply = () => {
    if (proposal === null) return
    const next = { ...draft, content: proposal }
    setDraft(next)
    setProposal(null)
    edit.mutate(next, { onError: (error) => toast.error(errorMessage(error)) })
  }

  const onSend = async () => {
    if (!(await save())) return
    send.mutate(notice.group, {
      onSuccess: (result) => {
        if (result.status === 'PARTIAL')
          toast.error(`${result.failedCount}명에게 보내지 못했어요. 다시 보낼 수 있어요.`)
        else toast.success(`${result.sentCount}명에게 보냈어요.`)
        void navigate(closePath)
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  }

  const remaining = notice.recipientCount - notice.sentCount
  // 다음 전형 안내(다음 전형의 안내)나 최종 합격 안내(입사 안내)의 칸이 비어 있으면 보내기 전에 묻는다.
  // 기타 안내는 비어도 묻지 않는다. 입사 안내는 이 화면에서 고치는 중인 값으로 본다
  const guideMissing = final
    ? emptyFields(ONBOARDING_FIELDS, onboarding).map((field) => field.label)
    : notice.guideMissing
  const hasGuide = final
    ? ONBOARDING_FIELDS.some((field) => onboarding[field.key].trim())
    : Boolean(notice.guide)
  const missingGuide =
    (notice.templateType === 'NEXT_STAGE' || final) &&
    notice.status === 'DRAFT' &&
    guideMissing.length > 0
  const guideName = final ? '입사 안내' : '다음 전형 안내'
  const goFillGuide = () => {
    if (final) {
      setConfirmingGuide(false)
      document.getElementById(ONBOARDING_ID)?.scrollIntoView({ block: 'center' })
    } else void save().then((ok) => ok && navigate(guidesPath))
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-bold">{notice.label}</h1>
        <span className="text-xs text-muted-foreground">{stageName} 종료 · ② 합격·불합격 안내</span>
        {waitingSchedule && scheduling.data && (
          <span className="ml-auto text-xs text-amber-700">
            다음 면접 시간을 배정한 뒤 보낼 수 있어요.{' '}
            <Link to={closePath} className="underline underline-offset-2">
              배정 상태 보기
            </Link>
          </span>
        )}
        <Button
          className={cn(!(waitingSchedule && scheduling.data) && 'ml-auto')}
          disabled={
            !(editable || notice.status === 'PARTIAL') ||
            send.isPending ||
            proposal !== null ||
            waitingSchedule
          }
          onClick={() => (missingGuide ? setConfirmingGuide(true) : void onSend())}
        >
          {send.isPending ? <LoaderCircle className="animate-spin" /> : <Send />}
          {send.isPending
            ? '보내는 중…'
            : notice.status === 'PARTIAL'
              ? `실패한 ${notice.failedCount}명에게 다시 발송`
              : `${remaining}명에게 발송`}
        </Button>
        {send.isPending && (
          <div
            role="status"
            aria-live="polite"
            className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 backdrop-blur-sm"
          >
            <div className="space-y-2 rounded-xl border bg-background px-8 py-6 text-center shadow-lg">
              <LoaderCircle className="mx-auto size-7 animate-spin text-muted-foreground" />
              <p className="font-semibold">메일을 보내고 있어요</p>
              <p className="text-sm text-muted-foreground">
                {notice.status === 'PARTIAL' ? notice.failedCount : remaining}명에게 보내는
                중이에요. 다 보낼 때까지 이 화면을 닫지 말아 주세요.
              </p>
            </div>
          </div>
        )}
        <AlertDialog open={confirmingGuide} onOpenChange={setConfirmingGuide}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {hasGuide ? `${guideName}에 비어 있는 칸이 있어요` : `${guideName}가 비어 있어요`}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {hasGuide
                  ? `비어 있는 칸: ${guideMissing.join(', ')}. 그대로 보내면 이 칸은 메일에서 빠져요.`
                  : final
                    ? `그대로 보내면 '${ONBOARDING_LATER}'라고 보내요.`
                    : '전형 결과 화면의 다음 전형 안내에 일정, 장소 같은 안내를 입력하면 메일 아래에 함께 보내요. 그대로 보내면 합격 결과와 다음 전형 이름만 보내요.'}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel onClick={goFillGuide}>입력하러 가기</AlertDialogCancel>
              <AlertDialogAction onClick={() => void onSend()}>그대로 보내기</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
      <div className="flex min-h-0 flex-1">
        <aside className="w-[180px] shrink-0 space-y-2 border-r p-3">
          <div className="px-1 pb-1 text-xs text-muted-foreground">안내 그룹</div>
          {notices.map((item) => (
            <Link
              key={item.group}
              to={`${closePath}/notices/${item.group}`}
              className={cn(
                'block rounded-lg border p-3',
                item.group === notice.group && 'border-foreground',
              )}
            >
              <div className="text-sm font-semibold">{item.label}</div>
              <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                {item.group === 'PASS' ? '합격' : '불합격'} {item.recipientCount}명
                <span
                  className={cn(
                    'rounded px-1 py-0.5 text-[11px] font-semibold',
                    noticeBadge(item).className,
                  )}
                >
                  {noticeBadge(item).label}
                </span>
              </div>
            </Link>
          ))}
        </aside>
        <div className="min-w-0 flex-1 overflow-auto bg-surface/40 p-6">
          <Tabs
            value={view}
            onValueChange={(value) => void changeView(value)}
            className="mx-auto mb-3 max-w-[560px]"
          >
            <TabsList>
              <TabsTrigger value="edit">편집</TabsTrigger>
              <TabsTrigger value="preview">보낼 모습</TabsTrigger>
            </TabsList>
          </Tabs>
          {view === 'preview' ? (
            <div className="mx-auto w-fit">
              <MailFrame
                preview={preview.data}
                title={`${notice.label} 미리보기`}
                settingsLink="메일 색 · 로고 바꾸기"
                scale={PREVIEW_SCALE}
              />
            </div>
          ) : (
            <div className="mx-auto max-w-[560px] rounded-xl border bg-background p-5 text-sm">
              <div className="flex items-center gap-3 border-b pb-3">
                <span className="text-xs text-muted-foreground">제목</span>
                <VariableField
                  aria-label="제목"
                  value={draft.subject}
                  onChange={(subject) => setDraft((current) => ({ ...current, subject }))}
                  className="flex-1 font-semibold"
                />
              </div>
              <div className="space-y-2 py-3">
                <VariableField
                  aria-label="인사말"
                  value={draft.greeting}
                  onChange={(greeting) => setDraft((current) => ({ ...current, greeting }))}
                />
                {proposal !== null ? (
                  <div className="space-y-2 px-3">
                    <p className="leading-6">
                      {sentenceDiff(draft.content, proposal).map((part, index) => (
                        <span
                          key={index}
                          className={cn(
                            part.kind === 'removed' && 'bg-fail text-fail-foreground line-through',
                            part.kind === 'added' && 'bg-pass',
                          )}
                        >
                          {part.text}{' '}
                        </span>
                      ))}
                    </p>
                    <div className="flex gap-2">
                      <Button size="sm" onClick={apply}>
                        적용
                      </Button>
                      <Button size="sm" variant="outline" onClick={() => setProposal(null)}>
                        되돌리기
                      </Button>
                    </div>
                  </div>
                ) : (
                  <Textarea
                    aria-label="안내 내용"
                    value={draft.content}
                    disabled={!editable}
                    onChange={(event) =>
                      setDraft((current) => ({ ...current, content: event.target.value }))
                    }
                    rows={5}
                    className="resize-none border-dashed"
                  />
                )}
                {final && editable ? (
                  <div id={ONBOARDING_ID} className="space-y-2 rounded-lg bg-muted/50 px-3 py-3">
                    <p className="text-xs text-muted-foreground">
                      <span className="font-semibold text-foreground">입사 안내</span> · 본문 아래에
                      목록으로 붙어요. 모두 비워 두면 &lsquo;{ONBOARDING_LATER}&rsquo;가 들어가요
                    </p>
                    <GuideFields
                      name="입사 안내"
                      fields={ONBOARDING_FIELDS}
                      values={onboarding}
                      disabled={!editable}
                      onChange={(key, value) =>
                        setOnboarding((current) => ({ ...current, [key]: value }))
                      }
                    />
                  </div>
                ) : (
                  notice.guide && (
                    <div className="space-y-1 rounded-lg bg-muted/50 px-3 py-2">
                      <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Lock className="size-3.5" />
                        {final ? (
                          '보낸 입사 안내'
                        ) : (
                          <>
                            보낼 때 붙는 다음 전형 안내 ·
                            <Link to={guidesPath} className="underline">
                              전형 결과 화면에서 고치기
                            </Link>
                          </>
                        )}
                      </p>
                      <p className="leading-6 whitespace-pre-line">
                        {notice.guide.split('\n').map((line, index) => (
                          <Fragment key={index}>
                            {index > 0 && '\n'}
                            {line}
                            {notice.interviewTimeHint && line.startsWith('- 일정:') && (
                              <span className="block pl-3 text-[11px] leading-4 text-muted-foreground">
                                {INTERVIEW_TIME_HINT}
                              </span>
                            )}
                          </Fragment>
                        ))}
                      </p>
                    </div>
                  )
                )}
                {notice.applicationNoLine && (
                  <div className="space-y-1 rounded-lg bg-muted/50 px-3 py-2">
                    <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Lock className="size-3.5" />
                      블라인드 채용이라 보낼 때 붙는 지원번호 안내
                    </p>
                    <p className="leading-6">{notice.applicationNoLine}</p>
                  </div>
                )}
                <VariableField
                  aria-label="맺음말"
                  value={draft.closing}
                  onChange={(closing) => setDraft((current) => ({ ...current, closing }))}
                />
              </div>
              <p className="flex items-center gap-1.5 border-t pt-3 text-xs text-muted-foreground">
                <Lock className="size-3.5" />
                {notice.requiredText}
              </p>
            </div>
          )}
          {view === 'edit' && editable && dirty && (
            <div className="mx-auto mt-3 flex max-w-[560px] justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={edit.isPending || saveOnboarding.isPending}
                onClick={() => void save().then((ok) => ok && toast.success('초안을 저장했어요.'))}
              >
                저장
              </Button>
            </div>
          )}
        </div>
        <AiRequestPanel
          messages={messages}
          examples={EXAMPLES}
          pending={ai.isPending}
          disabled={!editable}
          onSend={(message) => void request(message)}
          onReset={() => setMessages([])}
        />
      </div>
    </div>
  )
}
