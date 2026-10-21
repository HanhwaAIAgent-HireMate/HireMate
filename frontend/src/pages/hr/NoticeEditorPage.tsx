import { Lock, Send } from 'lucide-react'
import { useState } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import { VariableField } from '@/features/company/VariableField'
import {
  NOTICE_STATUS,
  useEditNotice,
  useNoticeAiRequest,
  useNotices,
  useSendNotice,
  type Notice,
} from '@/features/notice/api'
import { sentenceDiff } from '@/features/notice/sentenceDiff'
import { STAGE_GUIDES_ID } from '@/features/notice/StageGuides'
import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { useStageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { cn } from '@/lib/utils'

const EXAMPLES = [
  '불합격 안내 말투를 조금 더 따뜻하게 바꿔줘',
  '내용을 짧게 줄여줘',
  '추가: 문의는 recruit@example.com으로 해 주세요.',
]

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
  if (!overview.data || !notice) {
    return (
      <div className="p-6">
        <h1 className="sr-only">안내 초안</h1>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }
  return (
    <Editor
      key={`${notice.group}-${notice.content}`}
      notice={notice}
      notices={notices.data ?? []}
      stageName={overview.data.name}
      closePath={`/hr/recruitments/${overview.data.recruitmentId}/stages/${stageId}/close`}
      guidesPath={`/hr/recruitments/${overview.data.recruitmentId}/posting#${STAGE_GUIDES_ID}`}
    />
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
  /** 공고 작성 화면의 전형별 안내 칸 */
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
  const [proposal, setProposal] = useState<string | null>(null)
  const [messages, setMessages] = useState<AiMessage[]>([])
  const edit = useEditNotice(notice.stageId, notice.group)
  const send = useSendNotice(notice.stageId)
  const ai = useNoticeAiRequest(notice.stageId, notice.group)
  const editable = notice.status === 'DRAFT'
  const dirty =
    draft.subject !== notice.subject ||
    draft.greeting !== notice.greeting ||
    draft.content !== notice.content ||
    draft.closing !== notice.closing

  const save = async () => {
    if (!dirty) return true
    try {
      await edit.mutateAsync(draft)
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
      setMessages((current) => [...current, { role: 'ai', text: errorMessage(error) }])
    }
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
  // 다음 전형 안내인데 다음 전형의 안내(일정 · 장소 등)가 없으면 보내기 전에 묻는다
  const missingGuide =
    notice.templateType === 'NEXT_STAGE' && notice.status === 'DRAFT' && !notice.guide

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b px-6 py-4">
        <h1 className="text-xl font-bold">{notice.label}</h1>
        <span className="text-xs text-muted-foreground">{stageName} 종료 · ② 합격·불합격 안내</span>
        <Button
          className="ml-auto"
          disabled={
            !(editable || notice.status === 'PARTIAL') || send.isPending || proposal !== null
          }
          onClick={() => (missingGuide ? setConfirmingGuide(true) : void onSend())}
        >
          <Send />
          {notice.status === 'PARTIAL'
            ? `실패한 ${notice.failedCount}명에게 다시 발송`
            : `${remaining}명에게 발송`}
        </Button>
        <AlertDialog open={confirmingGuide} onOpenChange={setConfirmingGuide}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>다음 전형 안내가 비어 있어요</AlertDialogTitle>
              <AlertDialogDescription>
                공고 작성의 전형별 안내에 일정, 진행 방식, 장소 같은 안내를 입력하면 메일 아래에
                함께 보내요. 그대로 보내면 합격 결과와 다음 전형 이름만 보내요.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel
                onClick={() => void save().then((ok) => ok && navigate(guidesPath))}
              >
                입력하러 가기
              </AlertDialogCancel>
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
                    NOTICE_STATUS[item.status].className,
                  )}
                >
                  {NOTICE_STATUS[item.status].label}
                </span>
              </div>
            </Link>
          ))}
        </aside>
        <div className="min-w-0 flex-1 overflow-auto bg-surface/40 p-6">
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
              {notice.guide && (
                <div className="space-y-1 rounded-lg bg-muted/50 px-3 py-2">
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Lock className="size-3.5" />
                    보낼 때 붙는 다음 전형 안내 ·
                    <Link to={guidesPath} className="underline">
                      공고 작성에서 고치기
                    </Link>
                  </p>
                  <p className="leading-6 whitespace-pre-line">{notice.guide}</p>
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
          {editable && dirty && (
            <div className="mx-auto mt-3 flex max-w-[560px] justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={edit.isPending}
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
