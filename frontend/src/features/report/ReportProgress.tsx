import { progressLabel, useReportProgress } from './progress'

/** Report Agent가 쓰는 중일 때의 진행 막대. 보통 걸린 시간에 견준 어림이다 */
export function ReportProgress({
  createdAt,
  expectedSeconds,
}: {
  createdAt: string | undefined
  expectedSeconds: number | undefined
}) {
  const progress = useReportProgress(createdAt, expectedSeconds)
  if (!progress) return null
  return (
    <div className="flex flex-col gap-1.5">
      <div
        role="progressbar"
        aria-label="리포트 작성 진행률"
        aria-valuenow={progress.percent}
        aria-valuemin={0}
        aria-valuemax={100}
        className="h-2 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full rounded-full bg-ai transition-[width] duration-700"
          style={{ width: `${progress.percent}%` }}
        />
      </div>
      <p className="flex justify-between text-xs text-muted-foreground">
        <span>{progressLabel(progress)}</span>
        <span>지난 리포트 작성 시간으로 어림했어요</span>
      </p>
    </div>
  )
}
