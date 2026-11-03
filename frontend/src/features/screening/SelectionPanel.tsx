import { Eraser, FileChartColumn, Table2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useRequestCompareReport } from '@/features/report/api'
import { AgentReportModal } from '@/features/report/AgentReportModal'
import { ReportWindow, type ReportTab } from '@/features/report/ReportWindow'
import { useSelection, useSelectionActions, type StageOverview } from '@/features/screening/api'
import { CandidateItem, RowButton } from '@/features/screening/CandidateItem'
import type { StageTab } from '@/features/screening/tabs'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'

/** 비교 리포트의 지원자 수 범위. backend와 같다 */
const MIN_COMPARED = 2
const MAX_COMPARED = 5

// 가운데 선택 지원자. AI가 고르거나 HR이 넣은 지원자를 모으는 작업 영역이고 탭마다 따로다
export function SelectionPanel({
  overview,
  tab,
  editable,
}: {
  overview: StageOverview
  tab: StageTab
  editable: boolean
}) {
  const stageId = overview.stageId
  const selection = useSelection(stageId, tab.id)
  const actions = useSelectionActions(stageId, tab.id)
  const { checked, toggleChecked, setChecked, open, showTable } = useStageUi()
  const rows = selection.data?.items ?? []
  const ids = rows.map((row) => row.applicationId)
  const allChecked = ids.length > 0 && ids.every((id) => checked.includes(id))
  const fail = (error: unknown) => toast.error(errorMessage(error))
  // 체크한 선택 지원자가 2명 이상이면 그 사람들로, 아니면 선택 지원자 전원으로 비교한다
  const checkedHere = ids.filter((id) => checked.includes(id))
  const compared = checkedHere.length >= MIN_COMPARED ? checkedHere : ids
  const comparable = compared.length >= MIN_COMPARED && compared.length <= MAX_COMPARED
  const requestReport = useRequestCompareReport(stageId)
  const [reportId, setReportId] = useState<string | null>(null)
  // 서류 전형은 전체 · 비교를 바꿔 보는 창으로 연다. 비교할 사람이 없으면 전체 화면부터 연다
  const isDocument = overview.type === 'DOCUMENT'
  const [reportWindow, setReportWindow] = useState<{
    key: number
    tab: ReportTab
    reportId: string | null
  } | null>(null)
  const openWindow = (tab: ReportTab, id: string | null) =>
    setReportWindow({ key: Date.now(), tab, reportId: id })
  const createReport = () => {
    if (isDocument && !comparable) {
      openWindow('distribution', null)
      return
    }
    requestReport.mutate(
      { applicationIds: compared, focus: '', brief: false },
      {
        onSuccess: (requested) =>
          isDocument ? openWindow('deep', requested.reportId) : setReportId(requested.reportId),
        onError: fail,
      },
    )
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 px-4 pt-3 pb-3">
        <h2 className="text-sm font-bold">
          선택 지원자{' '}
          <span className="ml-1 text-muted-foreground">{selection.data?.total ?? 0}</span>
        </h2>
        <div className="flex-1" />
        <Tooltip>
          <TooltipTrigger asChild>
            <span>
              <button
                onClick={createReport}
                disabled={(!comparable && !isDocument) || requestReport.isPending}
                className="inline-flex items-center gap-1 text-xs font-medium text-ai hover:text-ai/80 disabled:opacity-50"
              >
                <FileChartColumn className="size-3.5" />
                리포트 생성
              </button>
            </span>
          </TooltipTrigger>
          <TooltipContent>
            {comparable
              ? `${compared.length}명을 비교하는 리포트를 Report Agent가 만들어요${isDocument ? '. 분포도 바꿔 볼 수 있어요' : ''}`
              : isDocument
                ? `서류 지원자 전체 화면을 열어요. 선택 지원자 ${MIN_COMPARED}~${MAX_COMPARED}명을 체크하면 비교 리포트도 만들어요`
                : `선택 지원자 ${MIN_COMPARED}~${MAX_COMPARED}명을 체크하면 비교 리포트를 만들 수 있어요`}
          </TooltipContent>
        </Tooltip>
        {/* 표 보기는 서류 전형의 지원서 분석(평가 기준 · 인재상)으로 만든다 */}
        {overview.type === 'DOCUMENT' && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span>
                <button
                  onClick={() => showTable(true)}
                  disabled={rows.length === 0}
                  className="inline-flex items-center gap-1 text-xs font-medium text-ai hover:text-ai/80 disabled:opacity-50"
                >
                  <Table2 className="size-3.5" />표 보기
                </button>
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {rows.length > 0
                ? `선택 지원자 ${rows.length}명을 평가 기준 · 인재상별 표로 바로 비교해요`
                : '선택 지원자를 넣으면 표로 비교할 수 있어요'}
            </TooltipContent>
          </Tooltip>
        )}
        {editable && (
          <button
            onClick={() => actions.clear.mutate(undefined, { onError: fail })}
            disabled={rows.length === 0}
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground disabled:opacity-50"
          >
            <Eraser className="size-3.5" />
            비우기
          </button>
        )}
      </div>
      {rows.length > 0 && editable && (
        <label className="flex items-center gap-2 px-5 pb-2 text-xs font-medium">
          <Checkbox
            checked={allChecked}
            onCheckedChange={(value) =>
              setChecked(
                value === true
                  ? [...new Set([...checked, ...ids])]
                  : checked.filter((id) => !ids.includes(id)),
              )
            }
          />
          전체 선택
        </label>
      )}
      <div className="min-h-0 flex-1 space-y-2 overflow-auto px-4 pt-1.5 pb-4">
        {selection.isPending && <Skeleton className="h-14 w-full" />}
        {!selection.isPending && rows.length === 0 && (
          <div className="px-4 py-12 text-center text-sm text-muted-foreground">
            {editable
              ? '조건을 AI Chat에 말하거나 왼쪽 + 버튼으로 지원자를 넣어 보세요.'
              : '선택 지원자가 없어요.'}
          </div>
        )}
        {rows.map((row) => (
          <CandidateItem
            key={row.applicationId}
            row={row}
            documentStage={false}
            scoreStage={overview.type === 'ASSESSMENT'}
            bordered
            checkbox={
              editable
                ? {
                    checked: checked.includes(row.applicationId),
                    onChange: (value) => toggleChecked(row.applicationId, value),
                  }
                : undefined
            }
            action={
              editable && (
                <RowButton
                  kind="remove"
                  label={`${row.name} 빼기`}
                  onClick={() => actions.remove.mutate([row.applicationId], { onError: fail })}
                />
              )
            }
            onOpen={() => open({ applicationId: row.applicationId, name: row.name })}
          />
        ))}
      </div>
      <AgentReportModal stageId={stageId} reportId={reportId} onClose={() => setReportId(null)} />
      {reportWindow && (
        <ReportWindow
          key={reportWindow.key}
          stageId={stageId}
          initialTab={reportWindow.tab}
          initialReportId={reportWindow.reportId}
          onClose={() => setReportWindow(null)}
        />
      )}
    </div>
  )
}
