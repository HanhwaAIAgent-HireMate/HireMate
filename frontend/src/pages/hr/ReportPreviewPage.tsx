import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import { ReportModal } from '@/features/report/ReportModal'
import type { ReportView } from '@/features/report/types'

// 개발용 리포트 미리보기. backend 연동(2단계) 전에 Report Agent가 가상 지원자로 만든 결과를 실제 모달로 연다.
// 샘플(sample-*.json)은 로컬에만 두고 커밋하지 않는다. 개발 서버에서만 열린다
const SAMPLES = import.meta.glob<ReportView>('/src/features/report/sample-*.json', {
  import: 'default',
})

const LABELS: Record<string, string> = {
  brief: '지원자 비교 · 간략히',
  compare: '지원자 비교',
  stage: '서류 전형 결과',
}

export function ReportPreviewPage() {
  const [reports, setReports] = useState<[string, ReportView][]>([])
  const [opened, setOpened] = useState<ReportView | null>(null)

  useEffect(() => {
    void Promise.all(
      Object.entries(SAMPLES).map(async ([path, load]) => {
        const tag = path.match(/sample-(\w+)\.json$/)?.[1] ?? path
        return [tag, await load()] as [string, ReportView]
      }),
    ).then(setReports)
  }, [])

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-8">
      <h1 className="text-lg font-bold">리포트 미리보기 (개발용)</h1>
      <p className="text-sm text-muted-foreground">
        Report Agent가 가상 지원자로 만든 결과를 실제 리포트 모달로 열어요. 이름은 가상이에요.
      </p>
      {reports.length === 0 && (
        <p className="text-sm text-muted-foreground">
          샘플이 없어요. src/features/report/sample-*.json을 넣으면 여기에 나와요.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        {reports.map(([tag, report]) => (
          <Button key={tag} variant="outline" onClick={() => setOpened(report)}>
            {LABELS[tag] ?? tag} 열기
          </Button>
        ))}
      </div>
      <ReportModal
        report={opened}
        open={opened !== null}
        onOpenChange={(open) => !open && setOpened(null)}
      />
    </div>
  )
}
