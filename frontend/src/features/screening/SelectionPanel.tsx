import { Eraser, RotateCcw } from 'lucide-react'
import { toast } from 'sonner'

import { Checkbox } from '@/components/ui/checkbox'
import { Skeleton } from '@/components/ui/skeleton'
import { useSelection, useSelectionActions, type StageOverview } from '@/features/screening/api'
import { CandidateItem, RowButton } from '@/features/screening/CandidateItem'
import { useStageUi } from '@/features/screening/store'
import { errorMessage } from '@/lib/api/client'

// 가운데 선택 지원자. AI가 고르거나 HR이 넣은 지원자를 모으는 작업 영역이다
export function SelectionPanel({
  overview,
  editable,
}: {
  overview: StageOverview
  editable: boolean
}) {
  const stageId = overview.stageId
  const selection = useSelection(stageId)
  const actions = useSelectionActions(stageId)
  const { checked, toggleChecked, setChecked, open } = useStageUi()
  const rows = selection.data?.items ?? []
  const ids = rows.map((row) => row.applicationId)
  const allChecked = ids.length > 0 && ids.every((id) => checked.includes(id))
  const fail = (error: unknown) => toast.error(errorMessage(error))

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <h2 className="flex-1 text-sm font-bold">
          선택 지원자{' '}
          <span className="ml-1 text-muted-foreground">{selection.data?.total ?? 0}</span>
        </h2>
        {editable && overview.canRestore && (
          <button
            onClick={() => actions.restore.mutate(undefined, { onError: fail })}
            className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="size-3.5" />
            되돌리기
          </button>
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
      <div className="min-h-0 flex-1 space-y-2 overflow-auto px-4 pb-4">
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
    </div>
  )
}
