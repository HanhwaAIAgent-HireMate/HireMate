import { Copy } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

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
import { useStageGuides } from '@/features/notice/api'
import { MailFrame } from '@/features/notice/MailFrame'
import { STAGE_GUIDES_ID } from '@/features/notice/StageGuides'
import {
  usePosting,
  usePublishPosting,
  useReceiptPreview,
  type Posting,
} from '@/features/posting/api'
import { CareersHeader, CareersPosting } from '@/features/posting/CareersPosting'
import { careersPath } from '@/features/recruit/labels'
import { errorMessage } from '@/lib/api/client'
import { formatDateTime, toLocalInput } from '@/lib/format'
import { cn } from '@/lib/utils'

// PST-02 공고 게시. 채용 페이지를 미리 보고 접수 기간을 정한 뒤 HR이 게시한다
export function PostingPublishPage() {
  const { recruitmentId = '' } = useParams()
  const posting = usePosting(recruitmentId)
  if (!posting.data) {
    return (
      <div className="p-6">
        <h1 className="sr-only">공고 게시</h1>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }
  return <PublishForm posting={posting.data} />
}

function defaultPeriod() {
  const open = new Date()
  open.setMinutes(0, 0, 0)
  open.setHours(open.getHours() + 1)
  const close = new Date(open)
  close.setDate(close.getDate() + 14)
  close.setHours(23, 59, 0, 0)
  return { open: toLocalInput(open), close: toLocalInput(close) }
}

function PublishForm({ posting }: { posting: Posting }) {
  const navigate = useNavigate()
  const publish = usePublishPosting(posting.recruitmentId)
  const [initial] = useState(defaultPeriod)
  const [period, setPeriod] = useState(initial)
  const [device, setDevice] = useState<'mobile' | 'pc'>('pc')
  const [confirming, setConfirming] = useState(false)
  const receipt = useReceiptPreview(posting.recruitmentId)
  const guides = useStageGuides(
    posting.recruitmentId,
    posting.stages.map((stage) => stage.id).join(),
  )
  // 안내 칸이 빈 전형. 게시는 막지 않고 알린다 (일정은 게시 뒤에 정하기도 한다)
  const emptyGuides = (guides.data ?? []).filter((guide) => guide.missing.length > 0)
  const url = `${window.location.origin}${careersPath(posting.postingId)}`
  const valid =
    Boolean(period.open && period.close) && new Date(period.close) > new Date(period.open)
  const summary = [posting.content.employmentType, posting.content.career, posting.content.location]
    .filter(Boolean)
    .join(' · ')

  const submit = () =>
    publish.mutate(
      {
        openAt: new Date(period.open).toISOString(),
        closeAt: new Date(period.close).toISOString(),
      },
      {
        onSuccess: () => {
          toast.success('공고를 게시했어요.')
          void navigate(`/hr/recruitments/${posting.recruitmentId}/posting/status`)
        },
        onError: (error) => {
          setConfirming(false)
          toast.error(errorMessage(error))
        },
      },
    )

  const copy = async () => {
    await navigator.clipboard.writeText(url)
    toast.success('채용 페이지 주소를 복사했어요.')
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center border-b px-6 py-4">
        <h1 className="text-xl font-bold">공고 게시</h1>
        <div className="ml-auto flex gap-2">
          <Button
            variant="outline"
            onClick={() => void navigate(`/hr/recruitments/${posting.recruitmentId}/posting`)}
          >
            이전
          </Button>
          <Button
            onClick={() => setConfirming(true)}
            disabled={!valid || posting.status !== 'DRAFT'}
          >
            게시하기
          </Button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="min-w-0 flex-1 overflow-auto bg-surface/60 p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">채용 페이지 미리보기</h2>
            <div className="inline-flex rounded-lg border bg-background p-0.5 text-xs">
              {(['mobile', 'pc'] as const).map((value) => (
                <button
                  key={value}
                  onClick={() => setDevice(value)}
                  className={cn(
                    'rounded-md px-2.5 py-1',
                    device === value
                      ? 'bg-foreground font-semibold text-background'
                      : 'text-muted-foreground',
                  )}
                >
                  {value === 'mobile' ? '모바일' : 'PC'}
                </button>
              ))}
            </div>
          </div>
          <div
            className={cn(
              'mx-auto overflow-hidden rounded-xl border bg-background',
              device === 'mobile' ? 'max-w-[390px]' : 'max-w-[980px]',
            )}
          >
            <CareersHeader companyName={posting.companyName} />
            <div className="p-6">
              <CareersPosting
                narrow={device === 'mobile'}
                posting={{
                  postingId: posting.postingId,
                  companyName: posting.companyName,
                  content: posting.content,
                  notices: posting.notices,
                  stages: posting.stages,
                  documents: posting.documents,
                  openAt: new Date(period.open || initial.open).toISOString(),
                  closeAt: new Date(period.close || initial.close).toISOString(),
                  state: 'OPEN',
                }}
              />
            </div>
          </div>
        </div>
        <aside className="w-[340px] shrink-0 space-y-6 border-l p-6">
          <Field label="채용 페이지 주소">
            <div className="flex gap-2">
              <input
                readOnly
                aria-label="채용 페이지 주소"
                value={url}
                className="h-9 min-w-0 flex-1 rounded-lg border px-3 text-sm text-muted-foreground"
              />
              <Button
                variant="outline"
                size="icon-lg"
                aria-label="주소 복사"
                onClick={() => void copy()}
              >
                <Copy />
              </Button>
            </div>
          </Field>
          <Field label="접수 기간">
            <div className="space-y-2">
              <input
                type="datetime-local"
                aria-label="접수 시작"
                value={period.open}
                onChange={(event) =>
                  setPeriod((current) => ({ ...current, open: event.target.value }))
                }
                className="h-9 w-full rounded-lg border px-3 text-sm"
              />
              <input
                type="datetime-local"
                aria-label="접수 마감"
                value={period.close}
                onChange={(event) =>
                  setPeriod((current) => ({ ...current, close: event.target.value }))
                }
                className="h-9 w-full rounded-lg border px-3 text-sm"
              />
              <p className="text-xs text-muted-foreground">
                채용 페이지의 접수 기간이자 자동 마감 기준이에요.
              </p>
            </div>
          </Field>
          <Field label="접수 확인 메일">
            <div className="space-y-2">
              <MailFrame
                preview={receipt.data}
                title="접수 확인 메일 미리보기"
                settingsLink="메일 문장 · 색 · 로고 바꾸기"
              />
              <p className="text-xs text-muted-foreground">
                지원서를 내면 바로 이 메일이 가요. 문장은 설정 › 안내 메일에서 모든 공고에 같이
                정하고, 보내는 때의 문장이 나가요. 지원자 이름과 지원번호는 예시예요.
              </p>
            </div>
          </Field>
        </aside>
      </div>
      <AlertDialog open={confirming} onOpenChange={setConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>공고를 게시할까요?</AlertDialogTitle>
            <AlertDialogDescription>
              게시하면 공고 내용과 전형 절차는 바꿀 수 없어요. 전형 일정 · 장소는 게시한 뒤에도
              전형별 안내에서 고칠 수 있어요.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <dl className="divide-y border-y text-sm">
            <ConfirmRow label="공고명" value={posting.content.title} />
            <ConfirmRow
              label="공고 기간"
              value={
                valid ? `${formatDateTime(period.open)} ~ ${formatDateTime(period.close)}` : '-'
              }
            />
            <ConfirmRow label="채용 요약" value={summary || '-'} />
            <ConfirmRow
              label="전형 절차"
              value={posting.stages.map((stage) => stage.name).join(' → ')}
            />
          </dl>
          {emptyGuides.length > 0 && (
            <div className="space-y-1 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
              <p className="font-semibold">전형별 안내에 비어 있는 칸이 있어요</p>
              <ul className="space-y-0.5">
                {emptyGuides.map((guide) => (
                  <li key={guide.stageId}>
                    · {guide.name}: {guide.missing.join(', ')}
                  </li>
                ))}
              </ul>
              <p className="text-xs">안내는 게시한 뒤에도 입력할 수 있어요.</p>
            </div>
          )}
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            {emptyGuides.length > 0 && (
              <Button
                variant="outline"
                onClick={() =>
                  void navigate(
                    `/hr/recruitments/${posting.recruitmentId}/posting#${STAGE_GUIDES_ID}`,
                  )
                }
              >
                입력하러 가기
              </Button>
            )}
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault()
                submit()
              }}
              disabled={publish.isPending}
            >
              {emptyGuides.length > 0 ? '그대로 게시' : '게시'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="text-sm font-medium text-muted-foreground">{label}</div>
      {children}
    </div>
  )
}

function ConfirmRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-4 py-2.5">
      <dt className="w-16 shrink-0 text-muted-foreground">{label}</dt>
      <dd className="font-semibold">{value}</dd>
    </div>
  )
}
