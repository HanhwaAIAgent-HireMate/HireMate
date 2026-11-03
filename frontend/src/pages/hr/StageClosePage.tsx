import { ArrowRight, Check, FileChartColumn, Lock, Send } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'

import { useHeaderCrumb } from '@/app/header-store'
import { Button } from '@/components/ui/button'
import { InterviewSchedulingStatus } from '@/features/interview/InterviewSchedulingStatus'
import { Skeleton } from '@/components/ui/skeleton'
import {
  needsDraft,
  noticeBadge,
  useFinishStage,
  useNotices,
  type Notice,
} from '@/features/notice/api'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import {
  toReportView,
  useAgentReport,
  useOpenStageReport,
  useStageReports,
  type ReportSummary,
} from '@/features/report/api'
import { AgentReportModal } from '@/features/report/AgentReportModal'
import { ReportProgress } from '@/features/report/ReportProgress'
import { useStageOverview, type StageOverview } from '@/features/screening/api'
import { errorMessage } from '@/lib/api/client'
import { formatShortDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

// STG-09 · FIN-01 전형 종료 4단계: 결과 확정 → 합격 · 불합격 안내 → 전형 결과 리포트 → 전형 종료
// (마지막 전형은 채용 종료). 리포트는 안내를 모두 보낸 뒤 열리고, 전형 종료를 막지 않는다

/** 리포트 칸에 보여 줄 핵심 지표 */
const REPORT_METRICS = ['m-target', 'm-pass', 'm-pass-rate']
export function StageClosePage() {
  const { stageId = '' } = useParams()
  const overview = useStageOverview(stageId)
  const confirmed =
    overview.data && overview.data.status !== 'ACTIVE' && overview.data.status !== 'PENDING'
  const notices = useNotices(stageId, Boolean(confirmed))
  useHeaderCrumb(
    overview.data && {
      title: overview.data.recruitmentTitle,
      status: RECRUITMENT_STATUS_LABELS[overview.data.recruitmentStatus],
      careersPath: careersPath(overview.data.postingId),
    },
  )

  if (!overview.data) {
    return (
      <div className="p-6">
        <h1 className="sr-only">전형 종료</h1>
        <Skeleton className="h-60 w-full" />
      </div>
    )
  }
  if (!confirmed) {
    return (
      <div className="p-6">
        <h1 className="text-lg font-bold">전형 종료</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          전형 결과를 먼저 확정해 주세요.{' '}
          <Link
            className="underline"
            to={`/hr/recruitments/${overview.data.recruitmentId}/stages/${stageId}`}
          >
            전형 화면으로
          </Link>
        </p>
      </div>
    )
  }
  return <CloseSteps overview={overview.data} notices={notices.data} />
}

function CloseSteps({ overview, notices }: { overview: StageOverview; notices?: Notice[] }) {
  const navigate = useNavigate()
  const finish = useFinishStage(overview.stageId)
  const done = overview.status === 'DONE'
  const allSent = Boolean(
    notices?.every((notice) => notice.status === 'SENT' || notice.status === 'EMPTY'),
  )
  const index = overview.steps.findIndex((step) => step.stageId === overview.stageId)
  const next = overview.steps[index + 1]
  const { counts } = overview
  // 리포트는 안내를 모두 보낸 뒤 열린다. 다 쓴 리포트가 있으면 리포트 단계도 끝난 것으로 본다
  // 평가 · 면접 전형은 전형 결과 리포트를 쓰지 않는다. 전형 흐름은 채용 최종 리포트가 모아 보여 준다
  const hasReport = overview.type === 'DOCUMENT'
  const reports = useStageReports(overview.stageId)
  const latest = reports.data?.find((report) => report.status !== 'FAILED') ?? null
  const finishStep = hasReport ? 4 : 3
  const step = done
    ? finishStep + 1
    : !allSent
      ? 2
      : !hasReport || latest?.status === 'DONE'
        ? finishStep
        : 3
  const sentGroups =
    notices?.filter((notice) => notice.status === 'SENT' || notice.status === 'EMPTY').length ?? 0
  const sentPeople = notices?.reduce((sum, notice) => sum + notice.sentCount, 0) ?? 0
  const waiting =
    notices
      ?.filter((notice) => notice.status !== 'SENT')
      .reduce((sum, notice) => sum + notice.recipientCount - notice.sentCount, 0) ?? 0
  const base = `/hr/recruitments/${overview.recruitmentId}/stages/${overview.stageId}`

  const onFinish = () =>
    finish.mutate(undefined, {
      onSuccess: (result) => {
        if (result.nextStageId) {
          toast.success(`${next?.name ?? '다음 전형'}을 시작했어요.`)
          void navigate(`/hr/recruitments/${overview.recruitmentId}/stages/${result.nextStageId}`)
        } else {
          toast.success('채용을 종료했어요. Report Agent가 최종 리포트를 쓰고 있어요.')
          void navigate(`/hr/recruitments/${overview.recruitmentId}/report`)
        }
      },
      onError: (error) => toast.error(errorMessage(error)),
    })

  return (
    <div>
      <div className="flex items-center gap-4 border-b px-6 py-4">
        <h1 className="text-xl font-bold">{overview.name} 종료</h1>
        <ol className="ml-auto flex items-center gap-2 text-sm">
          {[
            '결과 확정',
            '합격·불합격 안내',
            ...(hasReport ? ['전형 결과 리포트'] : []),
            overview.last ? '채용 종료' : '전형 종료',
          ].map((label, i) => (
            <li key={label} className="flex items-center gap-2">
              {i > 0 && <span className="h-px w-8 bg-border" />}
              <span
                className={cn(
                  'flex size-5 items-center justify-center rounded-full text-[11px] font-bold',
                  i + 1 < step
                    ? 'bg-pass-foreground text-white'
                    : i + 1 === step
                      ? 'bg-foreground text-background'
                      : 'border text-muted-foreground',
                )}
              >
                {i + 1 < step ? <Check className="size-3" /> : i + 1}
              </span>
              <span className={cn(i + 1 === step ? 'font-semibold' : 'text-muted-foreground')}>
                {label}
              </span>
            </li>
          ))}
        </ol>
      </div>
      <div
        className={cn(
          'mx-auto grid max-w-[1200px] items-start gap-4 p-6',
          hasReport ? 'grid-cols-3' : 'grid-cols-2',
        )}
      >
        <div className="flex flex-col gap-4">
          <StepCard
            title="합격·불합격 안내"
            active={step === 2}
            badge={step > 2 ? <Badge done>완료</Badge> : <Badge active>진행 중</Badge>}
          >
            <div className="space-y-2.5">
              {next?.type === 'INTERVIEW' && counts.pass > 0 && (
                <InterviewSchedulingStatus
                  stageId={overview.stageId}
                  guidesPath={`/hr/recruitments/${overview.recruitmentId}/posting#stage-guides`}
                />
              )}
              {!notices && <Skeleton className="h-20 w-full" />}
              {notices?.map((notice) => (
                <div
                  key={notice.group}
                  className={cn(
                    'rounded-lg border p-3',
                    notice.status === 'DRAFT' && 'border-foreground',
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold">{notice.label}</span>
                    <span
                      className={cn(
                        'rounded-md px-1.5 py-0.5 text-xs font-semibold',
                        noticeBadge(notice).className,
                      )}
                    >
                      {noticeBadge(notice).label}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {notice.group === 'PASS' ? '합격' : '불합격'} {notice.recipientCount}명
                    {notice.group === 'PASS' &&
                      notice.recipientCount > 0 &&
                      (next ? ` · ${next.name} 안내` : ' · 최종 합격 안내')}
                  </p>
                  {(notice.status === 'DRAFT' || notice.status === 'PARTIAL') && (
                    <Button size="sm" className="mt-2.5" asChild>
                      <Link to={`${base}/close/notices/${notice.group}`}>
                        {needsDraft(notice) ? 'AI 초안 쓰기' : '초안 확인·수정'} <ArrowRight />
                      </Link>
                    </Button>
                  )}
                </div>
              ))}
            </div>
            {notices && (
              <p className="mt-4 flex items-center gap-1.5 border-t pt-3 text-xs text-muted-foreground">
                <Send className="size-3.5" />
                발송 {sentGroups} / {notices.length} 그룹 · {sentPeople}명 발송, {waiting}명 대기
              </p>
            )}
          </StepCard>
          <StepCard title="결과 확정" badge={<Badge done>완료</Badge>}>
            <div className="grid grid-cols-3 gap-2">
              <Stat label="대상" value={counts.total} />
              <Stat label="합격" value={counts.pass} />
              <Stat
                label="불합격"
                value={counts.fail}
                note={
                  overview.undecidedAtConfirm > 0
                    ? `미결정 ${overview.undecidedAtConfirm}명 포함`
                    : undefined
                }
              />
            </div>
            <p className="mt-4 border-t pt-3 text-xs text-muted-foreground">
              {[
                overview.confirmedByName,
                overview.confirmedAt && formatShortDateTime(overview.confirmedAt),
              ]
                .filter(Boolean)
                .join(' · ')}{' '}
              확정
            </p>
          </StepCard>
        </div>
        {hasReport && (
          <ReportStep
            stageId={overview.stageId}
            open={allSent}
            latest={latest}
            active={step === 3}
            onRequested={() => void reports.refetch()}
          />
        )}
        <StepCard
          title={overview.last ? '채용 종료' : '전형 종료'}
          active={step === finishStep}
          badge={
            done ? (
              <Badge done>완료</Badge>
            ) : allSent ? (
              <Badge active>진행 중</Badge>
            ) : (
              <Badge>대기</Badge>
            )
          }
        >
          <dl className="space-y-2 text-sm">
            <Row label="지원" value={`${counts.total}명`} />
            <Row
              label={overview.last ? '최종 합격' : `합격 → ${next?.name ?? '다음 전형'}`}
              value={`${counts.pass}명`}
            />
            <Row
              label={overview.last ? `${overview.name} 불합격` : '불합격'}
              value={`${counts.fail}명`}
            />
          </dl>
          <Button
            className="mt-4 w-full"
            disabled={!allSent || done || finish.isPending}
            onClick={onFinish}
          >
            {done
              ? '종료한 전형이에요'
              : overview.last
                ? '채용 종료'
                : '전형 종료 · 다음 전형 시작'}
          </Button>
          {!allSent && !done && (
            <p className="mt-2 text-xs text-muted-foreground">
              안내를 모두 보내면 종료할 수 있어요.
            </p>
          )}
        </StepCard>
      </div>
    </div>
  )
}

/** 전형 결과 리포트 칸. 안내를 모두 보내면 열리고, 리포트 요약과 핵심 지표를 보여 준다 */
function ReportStep({
  stageId,
  open,
  latest,
  active,
  onRequested,
}: {
  stageId: string
  open: boolean
  latest: ReportSummary | null
  active: boolean
  onRequested: () => void
}) {
  const request = useOpenStageReport(stageId)
  const [modalId, setModalId] = useState<string | null>(null)
  // 리포트 내용은 안내를 모두 보낸 뒤에만 받을 수 있다
  const report = useAgentReport(stageId, open && latest ? latest.id : null)
  const view = report.data ? toReportView(report.data) : null
  const make = () =>
    request.mutate(undefined, {
      onSuccess: (opened) => {
        setModalId(opened.reportId)
        onRequested()
      },
      onError: (error) => toast.error(errorMessage(error)),
    })
  const metrics = view
    ? REPORT_METRICS.map((id) => view.bundle.metrics.find((metric) => metric.id === id)).filter(
        (metric) => metric !== undefined,
      )
    : []

  return (
    <StepCard
      title="전형 결과 리포트"
      active={active}
      badge={
        !open ? (
          <Badge>대기</Badge>
        ) : latest?.status === 'DONE' ? (
          <Badge done>완료</Badge>
        ) : (
          <Badge active>{latest?.status === 'PENDING' ? '작성 중' : '진행 중'}</Badge>
        )
      }
    >
      {!open ? (
        <div className="flex flex-col items-center gap-2 rounded-lg bg-muted/50 px-3 py-6 text-center">
          <Lock className="size-4 text-muted-foreground" />
          <p className="text-xs text-muted-foreground">
            합격·불합격 안내를 모두 보내면
            <br />
            Report Agent 리포트가 열려요.
          </p>
        </div>
      ) : latest?.status === 'PENDING' ? (
        <div className="space-y-3">
          <p className="text-sm font-semibold">Report Agent가 리포트를 쓰고 있어요</p>
          <ReportProgress
            createdAt={report.data?.createdAt}
            expectedSeconds={report.data?.expectedSeconds}
          />
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            onClick={() => setModalId(latest.id)}
          >
            진행 보기
          </Button>
        </div>
      ) : view ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
            <span className="font-bold text-ai">◇ Report Agent</span>
            <span className="text-muted-foreground">
              {formatShortDateTime(view.bundle.asOf)} 기준
            </span>
            {view.fallback && (
              <span className="rounded bg-fail px-1.5 py-0.5 font-semibold text-fail-foreground">
                기본 구성
              </span>
            )}
          </div>
          <p className="text-sm font-semibold">{view.spec.title}</p>
          <p className="line-clamp-4 text-xs leading-5 text-muted-foreground">
            {view.spec.summary}
          </p>
          {metrics.length > 0 && (
            <div className="grid grid-cols-3 gap-2 border-t pt-3">
              {metrics.map((metric) => (
                <div key={metric.id}>
                  <div className="text-[11px] text-muted-foreground">{metric.label}</div>
                  <div className="text-base font-bold">
                    {metric.value}
                    <span className="ml-0.5 text-[11px] font-medium text-muted-foreground">
                      {metric.unit}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
          <Button className="w-full" onClick={() => setModalId(latest?.id ?? null)}>
            <FileChartColumn />
            리포트 보기
          </Button>
        </div>
      ) : latest ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-muted-foreground">
            아직 리포트가 없어요. Report Agent가 전형 결과를 그래프와 근거로 정리해요.
          </p>
          <Button className="w-full" onClick={make} disabled={request.isPending}>
            <FileChartColumn />
            리포트 만들기
          </Button>
        </div>
      )}
      <AgentReportModal stageId={stageId} reportId={modalId} onClose={() => setModalId(null)} />
    </StepCard>
  )
}

function StepCard({
  title,
  badge,
  active,
  children,
}: {
  title: string
  badge: ReactNode
  active?: boolean
  children: ReactNode
}) {
  return (
    <section className={cn('rounded-xl border p-4', active && 'border-foreground')}>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-bold">{title}</h2>
        {badge}
      </div>
      {children}
    </section>
  )
}

function Badge({
  done,
  active,
  children,
}: {
  done?: boolean
  active?: boolean
  children: ReactNode
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-semibold',
        done
          ? 'bg-pass text-pass-foreground'
          : active
            ? 'bg-foreground text-background'
            : 'bg-muted text-muted-foreground',
      )}
    >
      {done && <Check className="size-3" />}
      {children}
    </span>
  )
}

function Stat({ label, value, note }: { label: string; value: number; note?: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
      {note && <div className="text-[11px] text-muted-foreground">{note}</div>}
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-bold">{value}</dd>
    </div>
  )
}
