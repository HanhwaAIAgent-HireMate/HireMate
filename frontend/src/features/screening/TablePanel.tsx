import { cn } from 'cn'
import { ArrowDown, ArrowLeft, MessageSquare } from 'lucide-react'
import { useState, type ThHTMLAttributes } from 'react'

import { Skeleton } from '@/components/ui/skeleton'
import {
  careerLabel,
  useRequirements,
  useSelection,
  type StageOverview,
} from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import {
  followUps,
  GROUP_LABELS,
  rowCells,
  TONE_CLASSES,
  useCandidateTable,
  useTableAnalyses,
  useTalentFits,
  type Cell,
  type TableFeature,
  type Tone,
} from '@/features/screening/table'
import type { StageTab } from '@/features/screening/tabs'

/** 열 이름을 눌러 정렬할 때의 순서: O · 상 → 중 → X · 하 → 확인 필요 → 분석 중 */
const TONE_ORDER: Record<Tone, number> = { good: 0, mid: 1, bad: 2, unknown: 3, waiting: 4 }

/** 열 너비(rem). 능력 열은 모두 같은 너비이고, 화면이 더 넓으면 같은 비율로 늘어난다 */
const NAME_WIDTH = 6
const BACKGROUND_WIDTH = 10
const FEATURE_WIDTH = 7
const FOLLOW_UP_WIDTH = 10

// 선택 지원자 표 보기 (대시보드). 저장된 분석을 그대로 옮겨 몇 초 안에 보여 준다.
// 가로 한 줄이 지원자 한 명, 세로 한 열이 같은 능력이다. 칸에는 판정만 보이고, 무엇을 했는지는 마우스를 올리면 보인다.
// 처음에는 상이 많은 순(같으면 중이 많은 순)이다. 열 이름을 누르면 그 열의 상 · 중 · 하 순으로 줄을 세우고(같으면 처음 순서),
// 한 번 더 누르면 처음 순서로 돌아간다
export function TablePanel({ overview, tab }: { overview: StageOverview; tab: StageTab }) {
  const stageId = overview.stageId
  const selection = useSelection(stageId, tab.id)
  const table = useCandidateTable(stageId)
  const required = useRequirements(stageId, overview.type === 'DOCUMENT')
  const { showTable, open, tableChat, showTableChat } = useStageUi()
  const [sortBy, setSortBy] = useState<string | null>(null)
  const rows = selection.data?.items ?? []
  const features = table.data?.features ?? []
  const analyses = useTableAnalyses(stageId, rows)
  const talents = useTalentFits(
    stageId,
    rows,
    features.some((feature) => feature.group === 'TALENT'),
  )
  const cells = rows.map((row, index) =>
    rowCells(row, features, analyses[index]?.data, talents[index]?.data),
  )
  const sortColumn = features.findIndex((feature) => feature.id === sortBy)
  // 처음 순서: 상(O)이 많은 사람, 같으면 중이 많은 사람, 그것도 같으면 선택 지원자에 넣은 순서
  const tally = (index: number, tone: Tone) =>
    (cells[index] ?? []).filter((item) => item.tone === tone).length
  const order = rows
    .map((_, index) => index)
    .sort((a, b) => tally(b, 'good') - tally(a, 'good') || tally(b, 'mid') - tally(a, 'mid'))
  if (sortColumn >= 0) {
    // Array.prototype.sort는 안정 정렬이라 같은 판정이면 처음 순서가 남는다
    order.sort(
      (a, b) =>
        TONE_ORDER[cells[a]?.[sortColumn]?.tone ?? 'waiting'] -
        TONE_ORDER[cells[b]?.[sortColumn]?.tone ?? 'waiting'],
    )
  }
  const groups = groupSpans(features)

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-3 px-4 pt-4 pb-3">
        <button
          onClick={() => showTable(false)}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          선택 지원자 {rows.length}
        </button>
        <h2 className="text-sm font-bold">표 보기</h2>
        <div className="ml-auto">
          <button
            type="button"
            onClick={() => showTableChat(!tableChat)}
            title="AI Chat은 표 오른쪽 끝에 접혀 있어요"
            className="inline-flex h-7 items-center gap-1.5 rounded-md border border-ai/40 bg-ai-soft px-2 text-xs font-medium text-ai hover:border-ai"
          >
            <MessageSquare className="size-3.5" />
            {tableChat ? 'AI Chat 접기' : 'AI Chat 열기 →'}
          </button>
        </div>
      </div>
      {/* 스크롤 칸에 좌우 여백을 두면 고정한 이름 열 왼쪽으로 다른 칸이 비쳐 보여, 여백은 바깥에 둔다 */}
      <div className="flex min-h-0 flex-1 flex-col px-4 pb-4">
        <div className="min-h-0 flex-1 overflow-auto">
          {table.isPending || selection.isPending ? (
            <Skeleton className="h-60 w-full" />
          ) : table.isError ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              표의 열을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.
            </p>
          ) : rows.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              선택 지원자가 없어요. 지원자를 넣으면 표로 비교할 수 있어요.
            </p>
          ) : features.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              평가 기준과 인재상이 없어 비교할 열이 없어요.
            </p>
          ) : (
            // 칸마다 오른쪽 · 아래 선을 긋고 표의 왼쪽 · 위 선을 더해 격자로 보이게 한다
            <table
              className="w-full table-fixed border-separate border-spacing-0 border-t border-l text-center text-xs"
              style={{
                minWidth: `${NAME_WIDTH + BACKGROUND_WIDTH + FEATURE_WIDTH * features.length + FOLLOW_UP_WIDTH}rem`,
              }}
            >
              <colgroup>
                <col style={{ width: `${NAME_WIDTH}rem` }} />
                <col style={{ width: `${BACKGROUND_WIDTH}rem` }} />
                {features.map((feature) => (
                  <col key={feature.id} style={{ width: `${FEATURE_WIDTH}rem` }} />
                ))}
                <col style={{ width: `${FOLLOW_UP_WIDTH}rem` }} />
              </colgroup>
              <thead>
                <tr>
                  <HeaderCell rowSpan={2} className="sticky left-0 z-20">
                    지원자
                  </HeaderCell>
                  <HeaderCell rowSpan={2}>업무 배경</HeaderCell>
                  {groups.map((group) => (
                    <HeaderCell key={group.group} colSpan={group.span} className="font-semibold">
                      {GROUP_LABELS[group.group]}
                    </HeaderCell>
                  ))}
                  <HeaderCell rowSpan={2}>추가 확인</HeaderCell>
                </tr>
                <tr>
                  {features.map((feature) => {
                    const mandatory = required.data?.includes(feature.id) ?? false
                    return (
                      <HeaderCell
                        key={feature.id}
                        aria-sort={sortBy === feature.id ? 'descending' : undefined}
                        className="p-0"
                      >
                        <button
                          type="button"
                          title={`${mandatory ? '필수 조건 · ' : ''}${feature.text}\n누르면 상 · 중 · 하 순으로 정렬해요`}
                          onClick={() => setSortBy(sortBy === feature.id ? null : feature.id)}
                          className={cn(
                            'inline-flex size-full items-center justify-center gap-0.5 px-1.5 py-2 font-semibold break-keep whitespace-normal hover:text-foreground',
                            sortBy === feature.id && 'text-foreground',
                            // 필수 조건 열은 보라색 이름으로 구분한다
                            mandatory && 'text-ai hover:text-ai',
                          )}
                        >
                          {feature.label}
                          {sortBy === feature.id && <ArrowDown className="size-3 shrink-0" />}
                        </button>
                      </HeaderCell>
                    )
                  })}
                </tr>
              </thead>
              <tbody>
                {order.map((index) => {
                  const row = rows[index]
                  if (!row) return null
                  const rowCellsHere = cells[index] ?? []
                  const checks = followUps(features, rowCellsHere)
                  return (
                    <tr key={row.applicationId}>
                      <td className="sticky left-0 z-10 border-r border-b bg-background px-2 py-2">
                        <button
                          onClick={() => open({ applicationId: row.applicationId, name: row.name })}
                          className="font-semibold hover:text-ai"
                        >
                          {row.name}
                        </button>
                      </td>
                      <td
                        title={careerLabel(row)}
                        className="truncate border-r border-b px-2 py-2 text-muted-foreground"
                      >
                        {careerLabel(row)}
                      </td>
                      {rowCellsHere.map((item, column) => (
                        <MarkCell key={features[column]?.id ?? column} cell={item} />
                      ))}
                      <td className="border-r border-b px-2 py-2 text-muted-foreground">
                        {checks.length > 0 ? checks.join(', ') : '-'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

function HeaderCell({ children, className, ...props }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={cn(
        'border-r border-b bg-background px-2 py-2 text-center font-medium whitespace-nowrap text-muted-foreground',
        className,
      )}
      {...props}
    >
      {children}
    </th>
  )
}

/** 칸에는 판정만 둔다. 무엇을 했는지와 판정 이유는 마우스를 올리면 보인다 */
function MarkCell({ cell }: { cell: Cell }) {
  const hint = [cell.note, cell.detail].filter(Boolean).join('\n')
  return (
    <td title={hint || undefined} className="border-r border-b px-2 py-2">
      <span
        className={cn(
          'inline-flex rounded-md px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap',
          hint && 'cursor-help',
          TONE_CLASSES[cell.tone],
        )}
      >
        {cell.mark}
      </span>
    </td>
  )
}

/** 묶음 머리글의 칸 수. 열은 자격요건 · 우대사항 · 인재상 순서로 온다 */
function groupSpans(features: TableFeature[]) {
  const spans: { group: TableFeature['group']; span: number }[] = []
  for (const feature of features) {
    const last = spans.at(-1)
    if (last?.group === feature.group) last.span += 1
    else spans.push({ group: feature.group, span: 1 })
  }
  return spans
}
