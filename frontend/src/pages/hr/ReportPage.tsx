import { Bot, Download, Link2 } from 'lucide-react'
import { useParams } from 'react-router'
import { toast } from 'sonner'

import { useHeaderCrumb } from '@/app/header-store'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { usePosting } from '@/features/posting/api'
import { careersPath, RECRUITMENT_STATUS_LABELS } from '@/features/recruit/labels'
import { useReport } from '@/features/report/api'
import { ApiError } from '@/lib/api/client'
import { formatShortDateTime } from '@/lib/format'

// RPT-01 최종 채용 리포트. 채용 종료 때 Report Agent가 쓰는 요약 문서이며 채용 상태를 바꾸지 않는다
export function ReportPage() {
  const { recruitmentId = '' } = useParams()
  const report = useReport(recruitmentId)
  const posting = usePosting(recruitmentId)
  useHeaderCrumb(
    posting.data && {
      title: posting.data.content.title,
      status: RECRUITMENT_STATUS_LABELS[posting.data.status],
      careersPath: careersPath(posting.data.postingId),
    },
  )

  if (!report.data) {
    const notReady = report.error instanceof ApiError && report.error.code === 'REPORT_NOT_READY'
    return (
      <div className="mx-auto max-w-[1040px] space-y-3 p-6">
        <h1 className="text-lg font-bold">채용 리포트</h1>
        {report.isError && !notReady ? (
          <p className="text-sm text-muted-foreground">
            리포트가 아직 없어요. 마지막 전형을 마치고 채용을 종료하면 만들어져요.
          </p>
        ) : (
          <>
            <p className="text-sm text-muted-foreground">
              Report Agent가 최종 리포트를 쓰고 있어요…
            </p>
            <Skeleton className="h-60 w-full" />
          </>
        )}
      </div>
    )
  }

  const { content } = report.data
  const copy = async () => {
    await navigator.clipboard.writeText(window.location.href)
    toast.success('리포트 링크를 복사했어요. 로그인한 담당자만 열 수 있어요.')
  }

  return (
    <article className="mx-auto max-w-[1040px] space-y-5 p-6 print:p-0">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-md bg-ai-soft px-2 py-0.5 text-xs font-medium text-ai">
          <Bot className="size-3" />
          {report.data.agent}
        </span>
        <span className="text-xs text-muted-foreground">
          {formatShortDateTime(report.data.generatedAt)} 기준 · 채용 종료 시 작성
        </span>
        <div className="ml-auto flex gap-2 print:hidden">
          <Button variant="outline" size="sm" onClick={() => window.print()}>
            <Download />
            PDF
          </Button>
          <Button variant="outline" size="sm" onClick={() => void copy()}>
            <Link2 />
            링크 복사
          </Button>
        </div>
      </div>
      <h1 className="text-xl font-bold">최종 채용 리포트 — {report.data.title}</h1>
      <p className="text-sm">{bold(content.summary)}</p>
      <div className="grid grid-cols-[1fr_380px] items-start gap-6">
        <div className="space-y-5">
          <table className="w-full overflow-hidden rounded-xl border text-sm">
            <thead className="bg-muted/50 text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2.5 text-left font-medium">전형</th>
                <th className="px-4 py-2.5 font-medium">대상</th>
                <th className="px-4 py-2.5 font-medium">합격</th>
                <th className="px-4 py-2.5 font-medium">불합격</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {content.stages.map((stage, index) => (
                <tr key={stage.name}>
                  <td className="px-4 py-2.5 font-semibold">{stage.name}</td>
                  <td className="px-4 py-2.5 text-center">{stage.target}</td>
                  <td
                    className={`px-4 py-2.5 text-center ${index === content.stages.length - 1 ? 'font-bold' : ''}`}
                  >
                    {stage.pass}
                  </td>
                  <td className="px-4 py-2.5 text-center">{stage.fail}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <section className="space-y-2">
            <h2 className="text-sm font-bold">특이사항</h2>
            {content.notes.length === 0 ? (
              <p className="text-sm text-muted-foreground">특이사항이 없어요.</p>
            ) : (
              <ul className="space-y-1 text-sm">
                {content.notes.map((note) => (
                  <li key={note}>· {note}</li>
                ))}
              </ul>
            )}
          </section>
        </div>
        <section>
          <h2 className="border-b pb-2 text-sm font-bold">최종 합격자 · 판단 근거</h2>
          {content.finalists.length === 0 && (
            <p className="py-3 text-sm text-muted-foreground">최종 합격자가 없어요.</p>
          )}
          <ul className="divide-y">
            {content.finalists.map((finalist) => (
              <li key={finalist.name} className="py-3">
                <p className="text-sm">
                  <span className="font-bold">{finalist.name}</span> · {finalist.reason}
                </p>
                {finalist.sources.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    출처 · {finalist.sources.join(' · ')}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </article>
  )
}

function bold(text: string) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, index) =>
      part.startsWith('**') && part.endsWith('**') ? (
        <strong key={index}>{part.slice(2, -2)}</strong>
      ) : (
        part
      ),
    )
}
