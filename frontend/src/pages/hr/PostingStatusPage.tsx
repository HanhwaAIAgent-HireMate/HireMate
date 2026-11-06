import { Copy, ExternalLink, Link2, Pencil } from 'lucide-react'
import { useState } from 'react'
import { useParams } from 'react-router'
import { Link } from 'react-router'
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
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Pager } from '@/components/Pager'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useHeaderCrumb } from '@/app/header-store'
import { DOCUMENT_LABELS, useApplications } from '@/features/apply/api'
import { useClosePosting, usePosting, type Posting } from '@/features/posting/api'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { WorkflowStepper } from '@/features/recruit/WorkflowStepper'
import { errorMessage } from '@/lib/api/client'
import { dDay, formatShortDateTime } from '@/lib/format'

// PST-03 공고 · 지원 접수 현황. Workflow의 첫 단계로, 마감하면 첫 전형이 전원 대상으로 시작된다
export function PostingStatusPage() {
  const { recruitmentId = '' } = useParams()
  const posting = usePosting(recruitmentId)
  useHeaderCrumb(
    posting.data && {
      title: posting.data.content.title,
      status: RECRUITMENT_STATUS_LABELS[posting.data.status],
      careersPath: careersPath(posting.data.postingId),
    },
  )
  if (!posting.data) {
    return (
      <div className="p-6">
        <h1 className="sr-only">공고 · 지원 접수</h1>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }
  return <StatusView posting={posting.data} />
}

/** 최근 지원자 한 쪽에 보이는 수 */
const APPLICANT_PAGE_SIZE = 5

function StatusView({ posting }: { posting: Posting }) {
  const close = useClosePosting(posting.recruitmentId)
  const [page, setPage] = useState(0)
  const applications = useApplications(posting.recruitmentId, APPLICANT_PAGE_SIZE, page)
  const total = applications.data?.total
  const pageCount = Math.ceil((total ?? 0) / APPLICANT_PAGE_SIZE)
  const url = `${window.location.origin}${careersPath(posting.postingId)}`
  const accepting = posting.status === 'PUBLISHED'
  // 시작한 전형은 눌러 그 전형 화면으로 간다. 끝난 전형은 화면만 볼 수 있다
  const stages = posting.stages.map((stage) => ({
    key: stage.id,
    label: stage.name,
    state:
      stage.status === 'DONE'
        ? ('done' as const)
        : stage.status === 'ACTIVE' || stage.status === 'CONFIRMED'
          ? ('ongoing' as const)
          : ('pending' as const),
    to: `/hr/recruitments/${posting.recruitmentId}/stages/${stage.id}`,
  }))

  const copy = async () => {
    await navigator.clipboard.writeText(url)
    toast.success('채용 페이지 주소를 복사했어요.')
  }

  return (
    <div>
      <WorkflowStepper
        items={[{ key: 'posting', label: '공고', count: total, state: 'active' }, ...stages]}
      />
      <div className="flex items-center gap-2 border-b px-5 py-4">
        <h1 className="text-lg font-bold">공고 · 지원 접수</h1>
        {posting.closeAt && (
          <span className="rounded-md bg-pass px-2 py-0.5 text-xs font-semibold text-pass-foreground">
            {accepting ? `접수 중 · ${dDay(posting.closeAt)}` : '마감'}
          </span>
        )}
        <div className="ml-auto flex gap-2">
          <Button variant="outline" asChild>
            <Link to={`/hr/recruitments/${posting.recruitmentId}/posting`}>
              <Pencil />
              공고 수정
            </Link>
          </Button>
          {accepting && (
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button>지금 마감</Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>지원 접수를 마감할까요?</AlertDialogTitle>
                  <AlertDialogDescription>
                    마감하면 채용 페이지에서 더 이상 지원할 수 없고,{' '}
                    {posting.stages[0]?.name ?? '첫 전형'}이 전원 대상으로 시작돼요.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>취소</AlertDialogCancel>
                  <AlertDialogAction
                    onClick={() =>
                      close.mutate(undefined, {
                        onSuccess: () => toast.success('접수를 마감했어요. 첫 전형이 시작됐어요.'),
                        onError: (error) => toast.error(errorMessage(error)),
                      })
                    }
                  >
                    마감
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          )}
        </div>
      </div>
      <div className="mx-auto max-w-[980px] space-y-4 p-5">
        <div className="flex items-center gap-3 rounded-xl border px-4 py-3">
          <Link2 className="size-4 text-muted-foreground" />
          <span className="min-w-0 flex-1 truncate text-sm font-semibold">{url}</span>
          <Button variant="outline" size="sm" asChild>
            <a href={careersPath(posting.postingId)} target="_blank" rel="noreferrer">
              <ExternalLink />
              열기
            </a>
          </Button>
          <Button variant="outline" size="sm" onClick={() => void copy()}>
            <Copy />
            주소 복사
          </Button>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div className="rounded-xl border p-4">
            <div className="text-xs text-muted-foreground">총 지원자</div>
            <div className="mt-1 flex items-baseline gap-1">
              <span className="text-2xl font-bold">{total ?? '-'}</span>
              <span className="text-xs text-muted-foreground">명</span>
            </div>
          </div>
          <div className="rounded-xl border p-4">
            <div className="text-xs text-muted-foreground">마감까지</div>
            <div className="mt-1 flex items-baseline gap-1.5">
              <span className="text-2xl font-bold">
                {posting.closeAt ? dDay(posting.closeAt) : '-'}
              </span>
              {posting.closeAt && (
                <span className="text-xs text-muted-foreground">
                  {formatShortDateTime(posting.closeAt)}
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="rounded-xl border">
          <div className="border-b px-4 py-2.5 text-xs font-medium text-muted-foreground">
            최근 지원자
          </div>
          {applications.data?.items.length === 0 && (
            <p className="px-4 py-8 text-center text-sm text-muted-foreground">
              아직 지원자가 없어요.
            </p>
          )}
          <ul className="divide-y">
            {applications.data?.items.map((item) => (
              <li key={item.applicationId} className="flex items-center gap-4 px-4 py-2.5 text-sm">
                <span className="w-16 font-semibold">{item.name}</span>
                <span className="w-24 text-xs text-muted-foreground">
                  {formatShortDateTime(item.submittedAt)}
                </span>
                <span className="flex flex-1 flex-wrap gap-1">
                  {item.documents.map((document) => (
                    <span key={document} className="rounded bg-muted px-1.5 py-0.5 text-xs">
                      {DOCUMENT_LABELS[document]}
                    </span>
                  ))}
                </span>
                <span className="text-xs text-muted-foreground">접수 완료</span>
              </li>
            ))}
          </ul>
          <Pager
            page={page}
            pageCount={pageCount}
            onChange={setPage}
            label="최근 지원자 쪽"
            className="border-t py-2"
          />
        </div>
      </div>
    </div>
  )
}
