import { ArrowLeft, Copy } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { DateTimePicker } from '@/components/DateTimePicker'
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
import { useCompanyProfile } from '@/features/company/api'
import { MailFrame } from '@/features/notice/MailFrame'
import {
  usePosting,
  usePublishPosting,
  useReceiptPreview,
  type Posting,
} from '@/features/posting/api'
import { CareersHeader, CareersPosting } from '@/features/posting/CareersPosting'
import { PostingStepHeader } from '@/features/posting/PostingStepHeader'
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
  const posterOnly = Boolean(posting.poster?.enabled)
  const formatLabel = posterOnly ? '포스터 공고' : '글 공고'
  const navigate = useNavigate()
  const publish = usePublishPosting(posting.recruitmentId)
  const [initial] = useState(defaultPeriod)
  const [period, setPeriod] = useState(initial)
  // 지난 시간은 고를 수 없게 한다. 기준은 페이지를 연 때이고, 게시할 때 지금 시간으로 다시 확인한다
  const [openedAt] = useState(() => toLocalInput(new Date()))
  // 채용 페이지 맨 아래의 회사 주소는 공고가 아니라 회사 소개에서 읽는다
  const company = useCompanyProfile()
  const [device, setDevice] = useState<'mobile' | 'pc'>('pc')
  const [confirming, setConfirming] = useState(false)
  const receipt = useReceiptPreview(posting.recruitmentId)
  const url = `${window.location.origin}${careersPath(posting.postingId)}`
  // 날짜는 달력에서만 고르므로 없는 날짜는 들어오지 않는다. 버튼만 막지 않고 이유를 알려 준다
  const periodProblem = !period.open
    ? '접수 시작 일시를 골라 주세요.'
    : !period.close
      ? '접수 마감 일시를 골라 주세요.'
      : new Date(period.close) <= new Date(period.open)
        ? '접수 마감은 접수 시작보다 뒤여야 해요.'
        : new Date(period.close) <= new Date(openedAt)
          ? '접수 마감은 지금보다 뒤여야 해요.'
          : null
  const valid = periodProblem === null
  // 시작을 앞으로 미루면 그때까지 채용 페이지에서 지원을 받지 않는다 (지원하면 '지금은 지원을 받지 않는 공고')
  const opensLater = valid && new Date(period.open) > new Date()
  const summary = [posting.content.employmentType, posting.content.career, posting.content.location]
    .filter(Boolean)
    .join(' · ')

  // 확인 창을 띄우는 사이 시작 시간이 지났으면 지금 시간으로 게시한다 (backend도 같게 고친다)
  const submit = () =>
    publish.mutate(
      {
        openAt: new Date(Math.max(new Date(period.open).getTime(), Date.now())).toISOString(),
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
      <PostingStepHeader title="공고 게시" caption={formatLabel}>
        <Button
          variant="outline"
          className="min-w-20"
          onClick={() =>
            void navigate(
              `/hr/recruitments/${posting.recruitmentId}/posting${posterOnly ? '/poster' : ''}`,
            )
          }
        >
          <ArrowLeft />
          이전
        </Button>
        <Button
          className="min-w-20"
          onClick={() => {
            if (new Date(period.close) <= new Date()) {
              toast.error('접수 마감 시간이 이미 지났어요. 다시 골라 주세요.')
              return
            }
            setConfirming(true)
          }}
          disabled={!valid || posting.status !== 'DRAFT'}
        >
          {formatLabel} 게시
        </Button>
      </PostingStepHeader>
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
                posterLogoUrl={`/api/recruitments/${posting.recruitmentId}/posting/poster/logo`}
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
                  poster: posting.poster,
                  companyAddress: company.data?.address ?? '',
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
              <DateTimePicker
                label="접수 시작"
                min={openedAt}
                value={period.open}
                onChange={(open) => setPeriod((current) => ({ ...current, open }))}
              />
              <DateTimePicker
                label="접수 마감"
                min={period.open > openedAt ? period.open : openedAt}
                value={period.close}
                onChange={(close) => setPeriod((current) => ({ ...current, close }))}
              />
              <p className="text-xs text-muted-foreground">
                채용 페이지의 접수 기간이자 자동 마감 기준이에요.
              </p>
              {periodProblem && (
                <p role="alert" className="text-xs text-destructive">
                  {periodProblem}
                </p>
              )}
              {opensLater && (
                <p className="text-xs text-muted-foreground">
                  접수 시작 전에는 채용 페이지에서 지원서를 받지 않아요.
                </p>
              )}
            </div>
          </Field>
          <Field label="접수 확인 메일">
            <div className="space-y-2">
              <MailFrame
                preview={receipt.data}
                title="접수 확인 메일 미리보기"
                settingsLink="메일 문장 · 색 · 로고 바꾸기"
                // 오른쪽 칸의 실제 폭에 메일 전체를 맞춰, 가로 · 세로 스크롤 없이 한 번에 본다
                scale="fit"
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
            <ConfirmRow label="게시 형식" value={formatLabel} />
            <ConfirmRow label="공고명" value={posting.content.title} />
            {posting.content.blind && (
              <ConfirmRow label="블라인드 채용" value="학력 · 출신 학교를 보지 않아요" />
            )}
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
          <RequiredSummary required={posting.required} />
          <AlertDialogFooter>
            <AlertDialogCancel>취소</AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault()
                submit()
              }}
              disabled={publish.isPending}
            >
              게시
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

/**
 * 서류 필수 조건. 공고 작성 화면에서 '필수'로 표시한 줄을 보여 주기만 한다(바꾸려면 [이전]으로 돌아가 고친다).
 * 지원자에게는 보이지 않는다
 */
function RequiredSummary({ required }: { required: Posting['required'] }) {
  const groups = [
    { label: '자격 요건', lines: required.qualifications },
    { label: '우대 사항', lines: required.preferred },
  ].filter((group) => group.lines.length > 0)
  const count = required.qualifications.length + required.preferred.length
  return (
    <div className="space-y-1.5 rounded-lg bg-muted p-3 text-sm">
      <p className="font-semibold">
        서류 필수 조건 {count}개
        <span className="ml-1.5 text-xs font-normal text-muted-foreground">
          지원자에게는 보이지 않아요
        </span>
      </p>
      {count === 0 ? (
        <p className="text-xs text-muted-foreground">
          필수로 표시한 줄이 없어요. 공고 작성에서 자격 요건 · 우대 사항 줄 끝의 [필수]로 표시할 수
          있어요.
        </p>
      ) : (
        groups.map((group) => (
          <div key={group.label}>
            <p className="text-xs text-muted-foreground">{group.label}</p>
            <ul className="space-y-0.5">
              {group.lines.map((line) => (
                <li key={line}>· {line}</li>
              ))}
            </ul>
          </div>
        ))
      )}
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
