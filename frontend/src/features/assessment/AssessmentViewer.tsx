import { ExternalLink, FileText, Link2 } from 'lucide-react'
import { useState } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import { NCS_AREAS, resultFileUrl, useAssessmentResult } from '@/features/assessment/api'
import type { CandidateDetail } from '@/features/screening/api'
import { DocumentViewer } from '@/features/screening/DocumentViewer'
import { cn } from '@/lib/utils'

/** 평가 전형의 지원자 카드 Viewer: 평가 결과(총점 · 영역 점수 · 등급) · 제출물과 지원 자료 */
export function AssessmentViewer({
  stageId,
  recruitmentId,
  detail,
}: {
  stageId: string
  recruitmentId: string
  detail: CandidateDetail
}) {
  const [tab, setTab] = useState<'result' | 'documents'>('result')
  const result = useAssessmentResult(stageId, detail.row.applicationId)
  const data = result.data

  return (
    <div className="space-y-4">
      <div role="tablist" className="flex gap-5 border-b text-sm">
        {(
          [
            ['result', '평가 결과'],
            ['documents', '지원 자료'],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn(
              '-mb-px border-b-2 pb-2',
              tab === key
                ? 'border-foreground font-semibold'
                : 'border-transparent text-muted-foreground',
            )}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === 'documents' ? (
        <DocumentViewer stageId={stageId} recruitmentId={recruitmentId} detail={detail} />
      ) : result.isPending ? (
        <Skeleton className="h-40 w-full" />
      ) : !data ? (
        <p className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground">
          아직 평가 결과가 없어요. Stage 바의 [평가 결과 등록]으로 결과표를 올리거나 직접 입력해요.
        </p>
      ) : (
        <div className="space-y-4 rounded-xl border p-4 text-sm">
          <div className="flex items-end gap-6">
            <div>
              <div className="text-xs text-muted-foreground">총점</div>
              <div className="text-3xl font-bold">
                {data.total !== null ? Number(data.total) : '-'}
              </div>
            </div>
            {data.grade && (
              <div>
                <div className="text-xs text-muted-foreground">등급</div>
                <div className="text-xl font-bold">{data.grade}</div>
              </div>
            )}
          </div>
          {Object.keys(data.areas).length > 0 && (
            <div className="space-y-2">
              {NCS_AREAS.filter((area) => area in data.areas).map((area) => {
                // 결과표에서 비운 영역은 null로 온다. 0점이 아니라 미입력으로 보여 준다
                const score: number | null = data.areas[area] ?? null
                return (
                  <div key={area} className="grid grid-cols-[96px_1fr_44px] items-center gap-3">
                    <span className="text-xs text-muted-foreground">{area}</span>
                    <div className="h-2 overflow-hidden rounded-full bg-muted">
                      {score !== null && (
                        <div
                          className="h-full rounded-full bg-foreground/70"
                          style={{ width: `${Math.min(100, Number(score))}%` }}
                        />
                      )}
                    </div>
                    {score === null ? (
                      <span className="text-right text-xs text-muted-foreground">미입력</span>
                    ) : (
                      <span className="text-right font-semibold tabular-nums">{Number(score)}</span>
                    )}
                  </div>
                )
              })}
            </div>
          )}
          {(data.fileId || data.url) && (
            <div className="space-y-2 border-t pt-3">
              <div className="text-xs text-muted-foreground">제출물</div>
              {data.fileId && (
                <a
                  href={resultFileUrl(stageId, detail.row.applicationId)}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                >
                  <FileText className="size-3.5" />
                  {data.fileName}
                  <ExternalLink className="size-3" />
                </a>
              )}
              {data.url && (
                <a
                  href={data.url}
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center gap-1.5 text-xs text-ai hover:underline"
                >
                  <Link2 className="size-3.5" />
                  {data.url}
                </a>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
