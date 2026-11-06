import { cn } from 'cn'
import { useMemo, useState, type ReactNode } from 'react'

import { chartFor, CHART_TYPES, peopleColors, type Chart, type ChartContext } from './charts'
import {
  crossCounts,
  evidenceParts,
  isScoreView,
  itemNames,
  meterOf,
  POSITIVE,
  SCORE_CELLS,
  topPercent,
  type EvidenceParts,
  type Meter,
  withItemNames,
} from './derive'
import { EChart } from './EChart'
import { SEQ, STATUS, word } from './palette'
import { NO_NAMES, usePrinting, useShownNames, whoOf, withNames } from './people'
import type { Block, ReportBundle, ReportKind, ReportView } from './types'

/** 부품이 6칸 격자에서 차지하는 칸. 줄이 남으면 그 줄 마지막 부품을 늘린다 */
const SPAN: Record<string, number> = {
  distribution: 4,
  // 도넛 · 레이더는 그림 오른쪽에 범례를 세로로 두어 반 폭이 필요하다
  donut: 3,
  cross: 2,
  share: 4,
  stacked: 3,
  bar: 3,
  radar: 3,
}

const SPAN_CLASS: Record<number, string> = {
  2: 'md:col-span-2',
  3: 'md:col-span-3',
  4: 'md:col-span-4',
  5: 'md:col-span-5',
  6: 'md:col-span-6',
}

/** 근거 카드는 안에서 근거를 접으므로 '자세히 보기'에 넣지 않는다. 비교 대상 누구의 근거도 숨기지 않는다 */
const ALWAYS_SHOWN = new Set(['evidence'])

/**
 * 처음 화면에 보이는 부품과 '자세히 보기'에 접는 부품. 격자 첫 줄(6칸)을 채우는 부품과 근거 카드만 보이고
 * 나머지는 접는다. 순서는 설계서 순서를 지킨다
 */
function splitShown(blocks: Block[]) {
  let used = 0
  const shown: Block[] = []
  const folded: Block[] = []
  for (const block of blocks) {
    if (used < 6 || ALWAYS_SHOWN.has(block.type)) {
      shown.push(block)
      used += SPAN[block.type] ?? 6
    } else folded.push(block)
  }
  return { shown, folded }
}

function pack(blocks: Block[]) {
  const spans: number[] = []
  let row = 0
  for (const block of blocks) {
    const size = SPAN[block.type] ?? 6
    if (row + size > 6) {
      spans[spans.length - 1] += 6 - row
      row = 0
    }
    spans.push(size)
    row = (row + size) % 6
  }
  if (row) spans[spans.length - 1] += 6 - row
  return spans
}

/** 부품이 그리는 데 쓰는 것. 문장 속 지원자번호에 이름을, 항목 코드에 항목 이름을 붙이는 text와 인쇄 중인지(printing)를 더한다 */
interface BodyContext extends ChartContext {
  text: (value: string) => string
  printing: boolean
  /** 비교 대상끼리 판정이 갈린 항목 key. 근거 카드에서 처음부터 펼쳐 둔다 */
  splits: Set<string>
}

/**
 * 리포트 본문. 설계서(spec)의 섹션과 부품을 묶음(bundle) 값으로 그린다.
 * 웹에서는 backend가 붙여 준 names로 '이름(지원자번호)'를 보여 주고, 인쇄(PDF)할 때는 지원자번호만 보여 준다
 */
/** 리포트 맨 아래 안내. 비교 리포트는 전형 중에도 만들므로 '확정된 결과'라고 쓰지 않는다 */
const FOOTNOTE: Record<ReportKind, string> = {
  STAGE: '이 리포트는 확정된 전형 결과를 요약할 뿐, 합격 · 불합격 결정을 바꾸지 않아요.',
  COMPARE: '이 리포트는 만든 시각의 판정과 근거를 견줄 뿐, 합격 · 불합격 결정을 바꾸지 않아요.',
  FINAL: '이 리포트는 확정된 채용 결과를 요약할 뿐, 합격 · 불합격 결정을 바꾸지 않아요.',
}

export function ReportBody({ report }: { report: ReportView }) {
  const { bundle, spec } = report
  const printing = usePrinting()
  const names = printing ? NO_NAMES : report.names
  const items = useMemo(() => itemNames(bundle), [bundle])
  const ctx = useMemo<BodyContext>(
    () => ({
      bundle,
      name: (number) => names[number] ?? null,
      who: (number) => whoOf(names, number),
      color: peopleColors(bundle.targets),
      text: (value) => withItemNames(withNames(value, names), items),
      printing,
      splits: new Set((spec.splits ?? []).map((split) => split.key)),
    }),
    [bundle, names, items, printing, spec.splits],
  )

  return (
    <div className="flex flex-col gap-5">
      {bundle.kind === 'COMPARE' && (
        <div className="flex flex-wrap gap-5 rounded-xl border bg-card px-4 py-2.5 text-sm">
          {bundle.targets.map((number) => (
            <Person key={number} number={number} ctx={ctx} />
          ))}
        </div>
      )}
      <p className="rounded-xl border bg-card px-4 py-3.5 text-[15px] leading-7">
        {!report.fallback && (
          <span className="mr-2 rounded bg-ai-soft px-1.5 py-0.5 align-[2px] text-[11px] font-bold text-ai">
            ◇ AI 요약
          </span>
        )}
        {ctx.text(spec.summary)}
      </p>
      {(spec.splits?.length ?? 0) > 0 && <SplitList splits={spec.splits ?? []} ctx={ctx} />}
      {spec.sections.map((section, index) => (
        <section key={index} className="flex flex-col gap-2.5" aria-label={ctx.text(section.title)}>
          <div className="flex items-center gap-2.5">
            <span className="rounded-md bg-ai-soft px-1.5 py-0.5 text-xs font-bold text-ai tabular-nums">
              {String(index + 1).padStart(2, '0')}
            </span>
            <h3 className="text-base font-bold">{ctx.text(section.title)}</h3>
          </div>
          {section.takeaway && (
            // 섹션 한 줄 요약은 Report Agent가 그 섹션의 표를 읽고 쓴 해석이다. 'AI 해석' 표시는 붙이지 않는다
            // 섹션의 답이라 카드 제목보다 먼저 눈에 들어오게 왼쪽 줄과 옅은 배경을 준다
            <p className="rounded-r-md border-l-[3px] border-ai bg-ai-soft/40 px-3 py-2 text-[14.5px] leading-6 font-semibold">
              {ctx.text(section.takeaway)}
            </p>
          )}
          <SectionBlocks blocks={section.blocks} ctx={ctx} />
        </section>
      ))}
      <p className="text-xs text-muted-foreground">{FOOTNOTE[bundle.kind]}</p>
    </div>
  )
}

/** 섹션의 부품 격자. 첫 줄만 보이고 나머지 부품은 '자세히 보기'에 접는다 */
function SectionBlocks({ blocks, ctx }: { blocks: Block[]; ctx: BodyContext }) {
  const { shown, folded } = splitShown(blocks)
  const grid = (list: Block[]) => (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
      {pack(list).map((span, i) => (
        <div
          key={i}
          className={cn(
            'flex min-w-0 flex-col rounded-xl border bg-card px-4 py-3.5',
            SPAN_CLASS[span],
          )}
        >
          <BlockView block={list[i]} ctx={ctx} />
        </div>
      ))}
    </div>
  )
  return (
    <>
      {grid(shown)}
      {folded.length > 0 && (
        <Fold
          printing={ctx.printing}
          summary={`자세히 보기 · ${folded.length}개 더`}
          className="text-[13px] font-semibold text-muted-foreground"
        >
          <div className="mt-2.5">{grid(folded)}</div>
        </Fold>
      )}
    </>
  )
}

/**
 * 접고 펼치는 칸. 처음 화면은 결론만 보이고 근거 · 자세한 내용은 눌러서 본다.
 * 인쇄(PDF)할 때는 누를 수 없으므로 모두 펼친다
 */
function Fold({
  summary,
  children,
  printing,
  open: initial = false,
  className,
}: {
  summary: ReactNode
  children: ReactNode
  printing: boolean
  open?: boolean
  className?: string
}) {
  const [open, setOpen] = useState(initial)
  return (
    <details
      open={printing || open}
      onToggle={(event) => {
        if (!printing) setOpen(event.currentTarget.open)
      }}
    >
      <summary
        className={cn(
          'w-fit cursor-pointer list-none rounded-md py-0.5 select-none hover:text-foreground print:hidden [&::-webkit-details-marker]:hidden',
          className,
        )}
      >
        <span className="inline-flex items-center gap-1.5">
          {summary}
          <span aria-hidden className="text-[10px]">
            {open ? '▲' : '▼'}
          </span>
        </span>
      </summary>
      {children}
    </details>
  )
}

/** 리포트 제목. 제목 속 지원자번호에 이름을 붙인다 (인쇄는 지원자번호만) */
export function ReportTitle({ report }: { report: ReportView }) {
  return withNames(report.spec.title, useShownNames(report.names))
}

/** 지원자 표기. 웹은 이름과 지원자번호, 인쇄는 지원자번호만 */
function Person({ number, ctx }: { number: string; ctx: ChartContext }) {
  const color = ctx.color(number)
  const name = ctx.name(number)
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      {color && <i className="inline-block size-2.5 rounded-full" style={{ background: color }} />}
      {name ? (
        <>
          <b>{name}</b>
          <span className="text-xs text-muted-foreground">{number}</span>
        </>
      ) : (
        <b>{number}</b>
      )}
    </span>
  )
}

function Chip({ value }: { value: string }) {
  const status = STATUS[value]
  if (!status) return <span className="text-xs">{word(value)}</span>
  return (
    <span
      className="block rounded-md px-1 py-1.5 text-xs font-semibold whitespace-nowrap"
      style={{ background: status.bg, color: status.fg }}
    >
      {status.icon} {status.label}
    </span>
  )
}

/** 둥근 차트 옆 범례. 색 칸 · 이름 · 값을 세 칸으로 맞춰 값이 한 줄로 정렬된다 */
function ChartLegend({ items }: { items: NonNullable<Chart['legend']> }) {
  return (
    <ul className="grid grid-cols-[auto_auto_auto] items-center gap-x-2 gap-y-2 text-[12.5px]">
      {items.map((item) => (
        <li key={item.label} className="contents">
          <i className="inline-block size-2.5 rounded-sm" style={{ background: item.color }} />
          <span>{item.label}</span>
          <b className="pl-2 text-right tabular-nums">{item.value}</b>
        </li>
      ))}
    </ul>
  )
}

/** 이보다 긴 그래프 설명은 한 줄만 보이고 '더보기'로 펼친다 */
const SHORT_CAPTION = 60

/** 부품 제목과 설명. 섹션의 읽을 점보다 한 단계 낮게 보이도록 작고 옅게 쓴다 */
function Head({
  title,
  caption,
  printing,
}: {
  title: string
  caption?: string
  printing: boolean
}) {
  return (
    <div className="mb-2.5">
      <div className="text-[13px] font-semibold text-foreground/80">{title}</div>
      {caption && <Caption text={caption} printing={printing} />}
    </div>
  )
}

function Caption({ text, printing }: { text: string; printing: boolean }) {
  const [open, setOpen] = useState(false)
  const long = text.length > SHORT_CAPTION
  return (
    <p className="mt-0.5 flex items-start gap-1.5 text-[12.5px] leading-5 text-muted-foreground">
      <span className={cn(long && !open && !printing && 'line-clamp-1')}>{text}</span>
      {long && !printing && (
        <button
          type="button"
          className="shrink-0 font-semibold whitespace-nowrap hover:text-foreground"
          onClick={() => setOpen(!open)}
        >
          {open ? '접기' : '더보기'}
        </button>
      )}
    </p>
  )
}

function BlockView({ block, ctx }: { block: Block; ctx: BodyContext }) {
  const { bundle } = ctx
  const caption = 'caption' in block ? block.caption : undefined
  const chart = useMemo(
    () => (CHART_TYPES.has(block.type) ? chartFor(block, ctx) : null),
    [block, ctx],
  )
  const title = ctx.text(block.title)
  const head = <Head title={title} caption={caption && ctx.text(caption)} printing={ctx.printing} />
  if (chart) {
    const picture = (
      <EChart option={chart.option} height={chart.height} label={title} still={ctx.printing} />
    )
    return (
      <>
        {head}
        {/* 옆 카드가 더 길어 카드가 늘어나면 그림을 위아래 가운데에 둔다 */}
        <div className="flex flex-1 flex-col justify-center">
          {chart.width ? (
            // 둥근 차트는 그림과 범례를 한 덩어리로 카드 가운데에 둔다. 좁으면 범례가 그림 아래로 내려간다
            <div className="flex flex-wrap items-center justify-center gap-x-8 gap-y-3">
              <div className="shrink-0" style={{ width: chart.width }}>
                {picture}
              </div>
              <ChartLegend items={chart.legend ?? []} />
            </div>
          ) : (
            picture
          )}
        </div>
      </>
    )
  }
  const facts = new Map(bundle.facts.map((f) => [`${f.applicant}|${f.key}`, f]))
  const label = (key: string) => bundle.facts.find((f) => f.key === key)?.label ?? key
  switch (block.type) {
    case 'kpi': {
      const metrics = block.metrics.flatMap((id) => bundle.metrics.find((m) => m.id === id) ?? [])
      return (
        <>
          {head}
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-[repeat(auto-fit,minmax(120px,1fr))]">
            {metrics.map((metric, i) => (
              <div
                key={metric.id}
                className={cn(
                  'flex flex-col rounded-lg border px-3 py-2.5',
                  i === 1 && 'border-pass/30 bg-pass/10',
                )}
              >
                <span className="text-xs text-muted-foreground">{metric.label}</span>
                <b className="text-2xl">
                  {metric.value}
                  <small className="ml-0.5 text-xs font-medium text-muted-foreground">
                    {metric.unit}
                  </small>
                </b>
              </div>
            ))}
          </div>
        </>
      )
    }
    case 'cross': {
      const counts = crossCounts(bundle, block.rowKey, block.colKey)
      const order = (values: string[]) =>
        [...new Set(values)].sort((a, b) => Number(!POSITIVE.has(a)) - Number(!POSITIVE.has(b)))
      const rows = order([...counts.keys()].map((cell) => cell.split('|')[0]))
      const cols = order([...counts.keys()].map((cell) => cell.split('|')[1]))
      return (
        <>
          {head}
          <table className="w-full border-separate border-spacing-1.5 text-xs">
            <thead>
              <tr>
                <th />
                {cols.map((col) => (
                  <th key={col} className="font-semibold text-muted-foreground">
                    {word(col)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row}>
                  <th className="text-left font-semibold whitespace-nowrap text-muted-foreground">
                    {word(row)}
                  </th>
                  {cols.map((col) => {
                    const agree = POSITIVE.has(row) === POSITIVE.has(col)
                    return (
                      <td
                        key={col}
                        className="rounded-lg border-[1.5px] py-3 text-center"
                        style={{
                          background: agree ? '#EEF4F0' : '#F7F0E1',
                          borderColor: agree ? 'transparent' : '#E2CDA0',
                        }}
                      >
                        <b className="block text-2xl">{counts.get(`${row}|${col}`) ?? 0}</b>
                        <span className="text-muted-foreground">명</span>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-muted-foreground">
            행 {label(block.rowKey)} · 열 {label(block.colKey)} · 엇갈린 칸은 황토색 테두리
          </p>
        </>
      )
    }
    case 'matrix':
    case 'table':
      return (
        <>
          {head}
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-[3px] text-xs">
              <thead>
                <tr>
                  <th />
                  {block.keys.map((key) => (
                    <th key={key} className="px-1 align-bottom font-semibold text-muted-foreground">
                      {label(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.applicants.map((number) => (
                  <tr key={number}>
                    <td className="pr-2 text-[12.5px] whitespace-nowrap">
                      <Person number={number} ctx={ctx} />
                    </td>
                    {block.keys.map((key) => {
                      const value = facts.get(`${number}|${key}`)?.value
                      return (
                        <td key={key} className="text-center">
                          {value === undefined ? (
                            '—'
                          ) : typeof value === 'number' ? (
                            value
                          ) : (
                            <Chip value={value} />
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )
    case 'position':
      return (
        <>
          {head}
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-[3px] text-xs">
              <thead>
                <tr>
                  <th />
                  {block.keys.map((key) => (
                    <th key={key} className="font-semibold text-muted-foreground">
                      {label(key)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.applicants.map((number) => (
                  <tr key={number}>
                    <td className="pr-2 text-[12.5px] whitespace-nowrap">
                      <Person number={number} ctx={ctx} />
                    </td>
                    {block.keys.map((key) => {
                      const top = topPercent(bundle, key, number) ?? 100
                      const level =
                        top <= 10 ? 4 : top <= 25 ? 3 : top <= 50 ? 2 : top <= 75 ? 1 : 0
                      return (
                        <td key={key}>
                          <span
                            className="flex flex-col rounded-md px-2 py-1.5"
                            style={{
                              background: SEQ[level],
                              color: level >= 3 ? '#fff' : undefined,
                            }}
                          >
                            <b className="text-[13px]">상위 {top}%</b>
                            <small className="opacity-85">
                              {facts.get(`${number}|${key}`)?.value}점
                            </small>
                          </span>
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )
    case 'rings': {
      const scores = block.views.every((view) => isScoreView(bundle, view.keys))
      return scores ? (
        <ScoreTable block={block} ctx={ctx} head={head} />
      ) : (
        <ViewTable block={block} ctx={ctx} title={title} caption={caption} />
      )
    }
    case 'evidence':
      return (
        <>
          {head}
          <EvidenceView block={block} ctx={ctx} />
        </>
      )
    case 'text':
      return (
        <>
          {head}
          <p className="text-[13.5px] leading-6">{ctx.text(block.text)}</p>
        </>
      )
    default:
      return head
  }
}

type RingsBlock = Extract<Block, { type: 'rings' }>

const EMPTY_CELL = '#E3E7ED'
/** 점수가 빈 칸에 그리는 빈 막대 */
const UNSCORED: Meter = { kind: 'score', value: 0, max: 0, filled: 0, cells: SCORE_CELLS }
/** 지원자 사이에 값이 다른 관점 줄의 배경 */
const DIFFERENT_ROW = '#F2F5FB'

/** 칸 막대. 채운 칸은 그 지원자 색, 빈 칸은 옅은 회색. 점수는 기울인 칸, 판정은 둥근 칸 */
function MeterCells({ meter, color }: { meter: Meter; color: string }) {
  const score = meter.kind === 'score'
  return (
    <span className="inline-flex items-center gap-[3px]" aria-hidden>
      {Array.from({ length: meter.cells }, (_, i) => (
        <i
          key={i}
          className={cn(
            'inline-block',
            score ? 'h-2.5 w-3.5 -skew-x-[20deg]' : 'h-2.5 w-5 rounded-full',
          )}
          style={{ background: i < meter.filled ? color : EMPTY_CELL }}
        />
      ))}
    </span>
  )
}

/** 영역 점수 표. 지원자마다 한 줄, 영역마다 10칸 막대와 점수, 마지막 칸에 총점 */
function ScoreTable({
  block,
  ctx,
  head,
}: {
  block: RingsBlock
  ctx: BodyContext
  head: ReactNode
}) {
  const { bundle } = ctx
  const totals = new Map(
    bundle.facts.filter((f) => f.key === bundle.totalKey).map((f) => [f.applicant, f]),
  )
  const showTotal = block.applicants.every((n) => totals.has(n))
  const max = (keys: string[]) => bundle.facts.find((f) => f.key === keys[0])?.max
  const totalMax = totals.get(block.applicants[0])?.max
  return (
    <>
      {head}
      <div className="overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b text-left text-xs">
              <th className="py-2 pr-3 font-semibold">지원자</th>
              {block.views.map((view) => (
                <th key={view.label} className="py-2 pr-3 font-semibold">
                  {view.label}
                  {max(view.keys) != null && ` · ${max(view.keys)}점`}
                </th>
              ))}
              {showTotal && (
                <th className="py-2 font-semibold">총점{totalMax != null && ` · ${totalMax}점`}</th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-border/60">
            {block.applicants.map((number) => {
              const color = ctx.color(number) ?? '#6A84B2'
              return (
                <tr key={number}>
                  <td className="py-3 pr-3">
                    <Person number={number} ctx={ctx} />
                  </td>
                  {block.views.map((view) => {
                    const meter = meterOf(bundle, view.keys, number)
                    return (
                      <td key={view.label} className="py-3 pr-3 whitespace-nowrap">
                        {meter?.kind === 'score' ? (
                          <span className="inline-flex items-center gap-2">
                            <MeterCells meter={meter} color={color} />
                            <span className="tabular-nums">{meter.value}</span>
                          </span>
                        ) : (
                          // 점수가 빈(보류) 지원자. 0점이 아니라 아직 매기지 않은 점수다
                          <span className="inline-flex items-center gap-2 text-xs text-muted-foreground">
                            <MeterCells meter={UNSCORED} color={EMPTY_CELL} />
                            확인 필요
                          </span>
                        )}
                      </td>
                    )
                  })}
                  {showTotal && (
                    <td className="py-3 font-semibold tabular-nums">{totals.get(number)?.value}</td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}

/** 관점별 항목 충족 표. 관점마다 한 줄, 지원자마다 항목 수만큼 칸. 지원자 사이에 값이 다른 줄은 배경으로 강조 */
function ViewTable({
  block,
  ctx,
  title,
  caption,
}: {
  block: RingsBlock
  ctx: BodyContext
  title: string
  caption?: string
}) {
  const { bundle } = ctx
  const rows = block.views.map((view) => {
    const meters = block.applicants.map((n) => meterOf(bundle, view.keys, n))
    const filled = new Set(meters.map((m) => m?.filled))
    return { view, meters, different: filled.size > 1 }
  })
  return (
    <>
      <div className="mb-2.5 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[13px] font-semibold text-foreground/80">{title}</div>
          {caption && <Caption text={ctx.text(caption)} printing={ctx.printing} />}
        </div>
        {rows.some((row) => row.different) && (
          <span className="text-xs text-muted-foreground">배경 강조 = 차이 있는 관점</span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-y-1 text-[13px]">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">평가 관점</th>
              {block.applicants.map((number) => (
                <th key={number} className="px-3 py-2 font-medium">
                  <Person number={number} ctx={ctx} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ view, meters, different }) => (
              <tr key={view.label} style={different ? { background: DIFFERENT_ROW } : undefined}>
                <td className="rounded-l-lg px-3 py-3">{view.label}</td>
                {meters.map((meter, i) => (
                  <td
                    key={block.applicants[i]}
                    className="px-3 py-3 whitespace-nowrap last:rounded-r-lg"
                  >
                    {meter ? (
                      <span className="inline-flex items-center gap-2">
                        <MeterCells
                          meter={meter}
                          color={ctx.color(block.applicants[i]) ?? '#6A84B2'}
                        />
                        <span className="tabular-nums">
                          {meter.kind === 'score'
                            ? `${meter.value}/${meter.max}`
                            : `${meter.met}/${meter.cells}`}
                        </span>
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">확인 필요</span>
                    )}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}

const AGENTS: Record<string, string> = {
  application: '서류 Agent',
  assessment: '직무역량 Agent',
  interview: '면접 Agent',
}

type EvidenceBlock = Extract<Block, { type: 'evidence' }>

/**
 * 지원자별 근거 카드. 항목마다 키워드 요약을 먼저 보여 주고, 그 아래 AI 분석(분석 Agent의 판단)과
 * 원문(지원자가 쓴 글자 그대로)을 나눠 보여 준다. 한 항목 안의 같은 원문은 한 번만 보여 준다
 */
function EvidenceView({ block, ctx }: { block: EvidenceBlock; ctx: BodyContext }) {
  const { bundle } = ctx
  const grouped = new Map<string, EvidenceBlock['items']>()
  for (const item of block.items)
    grouped.set(item.applicant, [...(grouped.get(item.applicant) ?? []), item])
  const order = [
    ...bundle.targets.filter((n) => grouped.has(n)),
    ...[...grouped.keys()].filter((n) => !bundle.targets.includes(n)),
  ]
  const known = new Set(bundle.evidence.map((evidence) => evidence.id))
  // 아무 지원자에게도 근거 문장이 없으면 똑같은 빈 카드를 늘어놓지 않고 한 상자로 알린다
  if (!block.items.some((item) => item.evidence.some((id) => known.has(id)))) {
    return (
      <div className="flex flex-col gap-2 rounded-lg bg-muted/40 px-4 py-3 text-[13px] leading-6">
        <p className="text-muted-foreground">
          이 지원자들의 서류 분석 근거 문장이 아직 없어요. 항목별 판정은 위 표에서 볼 수 있어요.
        </p>
        <ul className="flex flex-col gap-1">
          {order.map((number) => (
            <li key={number} className="flex flex-wrap items-baseline gap-x-2">
              <Person number={number} ctx={ctx} />
              <span className="text-xs text-muted-foreground">
                {(grouped.get(number) ?? [])
                  .map((item) => ctx.text(item.text))
                  .filter(Boolean)
                  .join(' · ')}
              </span>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-3">
      {order.map((number) => {
        const items = (grouped.get(number) ?? []).map((item) => ({
          item,
          parts: partsOf(item, bundle),
        }))
        const parts = [
          ...new Map(items.flatMap((entry) => entry.parts).map((p) => [p.id, p])).values(),
        ]
        const keywords = [...new Set(items.flatMap((entry) => entry.item.keywords ?? []))]
        // 판정이 갈린 항목은 비교 리포트에서 가장 궁금한 곳이라 처음부터 펼쳐 둔다
        const split = (part: EvidenceParts) => ctx.splits.has(criterionKey(number, part.id))
        // 같은 근거를 여러 근거 항목이 인용해도 한 줄로만 보여 준다
        const seen = new Set<string>()
        return (
          <div
            key={number}
            className="flex flex-col gap-2 rounded-r-lg border-l-4 bg-muted/40 px-4 py-3 text-[13px] leading-6"
            style={{ borderLeftColor: ctx.color(number) ?? '#C9CED6' }}
          >
            <Person number={number} ctx={ctx} />
            {keywords.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <Tag>키워드</Tag>
                {keywords.map((keyword) => (
                  <span
                    key={keyword}
                    className="rounded-md border bg-card px-2 py-px font-semibold"
                  >
                    {ctx.text(keyword)}
                  </span>
                ))}
              </div>
            )}
            <VerdictCounts parts={parts} />
            <Fold
              printing={ctx.printing}
              open={parts.some(split)}
              summary={parts.length > 0 ? `근거 보기 · ${parts.length}개` : '항목 보기'}
              className="text-xs font-semibold text-ai"
            >
              <div className="mt-1.5 flex flex-col gap-2">
                <QuantifiedQuotes items={grouped.get(number) ?? []} bundle={bundle} />
                <div className="flex flex-col divide-y divide-dashed">
                  {items.flatMap(({ item, parts: cited }, i) => {
                    const name =
                      (item.keywords ?? []).map(ctx.text).join(' · ') || ctx.text(item.text)
                    if (cited.length === 0)
                      return (
                        <p key={i} className="py-2 text-xs text-muted-foreground">
                          {name && `${name} · `}근거 문장 없음 · 다음 전형에서 확인
                        </p>
                      )
                    return cited
                      .filter((part) => !seen.has(part.id) && seen.add(part.id))
                      .map((part) => (
                        <PartRow
                          key={part.id}
                          part={part}
                          name={name}
                          open={split(part)}
                          ctx={ctx}
                        />
                      ))
                  })}
                </div>
              </div>
            </Fold>
          </div>
        )
      })}
    </div>
  )
}

/** 근거 id(e-{지원자번호}-{항목 코드})의 서류 항목 판정 key */
function criterionKey(applicant: string, id: string) {
  return `document.criterion.${id.slice(`e-${applicant}-`.length)}`
}

/** 근거 항목이 인용한 근거. 정량 원문이 받치는 판단을 먼저 둔다. 같은 강도 안에서는 모델이 고른 순서를 지킨다 */
function partsOf(item: EvidenceBlock['items'][number], bundle: ReportBundle) {
  return item.evidence
    .flatMap((id) => {
      const found = bundle.evidence.find((evidence) => evidence.id === id)
      return found ? [evidenceParts(bundle, found)] : []
    })
    .sort((a, b) => Number(b.strength === 'QUANT') - Number(a.strength === 'QUANT'))
}

/** 지원자 카드에서 접힌 근거의 판정 개수. 펼치지 않아도 충족 · 부분 · 미충족이 몇 개인지 보인다 */
function VerdictCounts({ parts }: { parts: EvidenceParts[] }) {
  const counts = new Map<string, number>()
  for (const part of parts)
    if (part.verdict && STATUS[part.verdict])
      counts.set(part.verdict, (counts.get(part.verdict) ?? 0) + 1)
  if (counts.size === 0) return null
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      {Object.keys(STATUS)
        .filter((verdict) => counts.has(verdict))
        .map((verdict) => (
          <span
            key={verdict}
            className="rounded px-1.5 py-px font-semibold"
            style={{ background: STATUS[verdict].bg, color: STATUS[verdict].fg }}
          >
            {STATUS[verdict].icon} {STATUS[verdict].label} {counts.get(verdict)}
          </span>
        ))}
    </div>
  )
}

/**
 * 근거 한 줄. 어느 항목의 판단인지(영역 · 항목 · 판정)만 보이고, 누르면 AI 분석(분석 Agent의 판단)과
 * 원문(지원자가 쓴 글자 그대로)을 펼친다. 항목 이름이 없는 예전 근거는 근거 항목의 키워드를 이름으로 쓴다
 */
function PartRow({
  part,
  name,
  open,
  ctx,
}: {
  part: EvidenceParts
  name: string
  open: boolean
  ctx: BodyContext
}) {
  const status = part.verdict ? STATUS[part.verdict] : undefined
  return (
    <div className="py-2 first:pt-1 last:pb-0">
      <Fold
        printing={ctx.printing}
        open={open}
        summary={
          <span className="flex flex-wrap items-center gap-1.5">
            {part.area && <span className="text-xs text-muted-foreground">{part.area}</span>}
            <span className="font-semibold">{part.label ?? name}</span>
            {status && (
              <span
                className="rounded px-1.5 py-px text-xs font-semibold"
                style={{ background: status.bg, color: status.fg }}
              >
                {status.icon} {status.label}
              </span>
            )}
          </span>
        }
      >
        <div className="mt-1.5 flex flex-col gap-2 pl-3">
          <div className="flex flex-col gap-1">
            <Tag>AI 분석</Tag>
            <p>
              {part.analysis}{' '}
              <span className="text-xs text-muted-foreground">
                · {AGENTS[part.agent] ?? part.agent}
              </span>
            </p>
          </div>
          {part.quote && (
            <div className="flex flex-col gap-1">
              <Tag>원문</Tag>
              <p
                className={cn(
                  'text-[12.5px] text-muted-foreground',
                  part.strength === 'CLAIM' && 'opacity-80',
                )}
              >
                {part.strength && <StrengthChip strength={part.strength} />}
                <span
                  className={cn('text-foreground', part.strength === 'QUANT' && 'font-semibold')}
                >
                  “{part.quote}”
                </span>{' '}
                · {part.source}
              </p>
            </div>
          )}
        </div>
      </Fold>
    </div>
  )
}

/**
 * 판정이 갈린 이유. Report Agent가 서류 Agent의 판정 세부(충족한 부분 · 못 채운 부분 · 역할)를 읽고 항목마다 한 문장으로
 * 쓴 것이다. 항목 이름을 앞에 두고, 문장이 인용한 근거 수를 붙인다. 모델이 쓰지 못한 항목은 코드가 판정만 적는다.
 */
function SplitList({
  splits,
  ctx,
}: {
  splits: NonNullable<ReportView['spec']['splits']>
  ctx: BodyContext
}) {
  const labels = new Map(ctx.bundle.facts.map((fact) => [fact.key, fact.label]))
  return (
    <section
      aria-label="판정이 갈린 이유"
      className="flex flex-col gap-2 rounded-xl border border-ai/30 bg-ai-soft/40 px-4 py-3.5"
    >
      <div className="flex flex-wrap items-baseline gap-2">
        <h3 className="text-sm font-bold text-ai">판정이 갈린 이유</h3>
        <span className="text-[11px] text-muted-foreground">
          AI가 서류 분석의 충족한 부분 · 못 채운 부분 · 역할을 읽고 정리했어요
        </span>
      </div>
      {/* 항목 이름과 근거 수만 먼저 보이고, 누가 무엇이 달랐는지는 눌러서 읽는다 */}
      <ul className="flex flex-col gap-1">
        {splits.map((split) => (
          <li key={split.key} className="text-[13px] leading-6">
            <Fold
              printing={ctx.printing}
              summary={
                <span>
                  <b>{labels.get(split.key) ?? split.key}</b>
                  {split.evidence.length > 0 && (
                    <span className="ml-1.5 text-[11px] text-muted-foreground">
                      · 근거 {split.evidence.length}건
                    </span>
                  )}
                </span>
              }
            >
              <p className="mt-0.5 pl-3">{ctx.text(split.text)}</p>
            </Fold>
          </li>
        ))}
      </ul>
    </section>
  )
}

/** 원문 안의 성과 수치(숫자 + 단위). 눈에 띄게 칠할 부분만 고르며, 정량 · 서술 판정은 ai가 한다 */
const FIGURE = /(\d[\d,.]*\s*(?:%|퍼센트|배|ms|초|분|시간|일|개월|건|회|번|개|원|만|억|TPS|QPS|x)?)/

/**
 * 지원자 카드 맨 위의 성과 수치 상자. 그 지원자가 인용된 근거 중 정량 원문만 모아 숫자를 칠해 먼저 보여 준다.
 * 정량 근거가 서술 근거보다 강하다는 위계를 화면에서 바로 읽게 한다. 정량 원문이 없으면 그렇다고 알린다.
 */
function QuantifiedQuotes({
  items,
  bundle,
}: {
  items: EvidenceBlock['items']
  bundle: ReportBundle
}) {
  const ids = new Set(items.flatMap((item) => item.evidence))
  // 근거가 하나도 없는 지원자는 아래 항목이 '확인되지 않았어요'를 알린다
  if (ids.size === 0) return null
  const quotes = [
    ...new Map(
      bundle.evidence
        .filter(
          (evidence) => ids.has(evidence.id) && evidence.strength === 'QUANT' && evidence.quote,
        )
        .map((evidence) => [evidence.quote, evidence] as const),
    ).values(),
  ]
  if (quotes.length === 0) {
    return (
      <p className="w-fit rounded-md bg-muted px-2.5 py-1 text-xs text-muted-foreground">
        성과 수치 없음 · 한 일만 적은 서술 근거예요. 규모와 성과는 면접에서 확인해요.
      </p>
    )
  }
  return (
    <div
      className="flex flex-col gap-1 rounded-md border px-3 py-2"
      style={{ borderColor: STATUS.MET.bar, background: STATUS.MET.bg }}
    >
      <span className="text-xs font-bold" style={{ color: STATUS.MET.fg }}>
        성과 수치 {quotes.length}건 · 숫자로 확인되는 강한 근거
      </span>
      {quotes.map((evidence) => (
        <p key={evidence.id} className="text-[13px]">
          “
          {(evidence.quote ?? '').split(FIGURE).map((part, index) =>
            index % 2 === 1 ? (
              <mark
                key={index}
                className="rounded px-0.5 font-bold"
                style={{ background: '#CFE5D7', color: STATUS.MET.fg }}
              >
                {part}
              </mark>
            ) : (
              part
            ),
          )}
          ”{' '}
          <span className="text-xs text-muted-foreground">
            · {evidence.label ?? evidence.source}
          </span>
        </p>
      ))}
    </div>
  )
}

/** 원문 강도 표시. 정량은 성과를 숫자로 적은 강한 근거, 서술은 한 일만 적은 약한 근거다 */
function StrengthChip({ strength }: { strength: 'QUANT' | 'CLAIM' }) {
  const quant = strength === 'QUANT'
  const status = quant ? STATUS.MET : STATUS.UNKNOWN
  return (
    <span
      title={
        quant
          ? '성과를 숫자로 적은 근거예요'
          : '한 일만 적은 근거예요. 규모 · 성과는 확인이 필요해요'
      }
      className="mr-1.5 inline-block rounded px-1.5 py-px align-[1px] text-[10.5px] font-semibold"
      style={{ background: status.bg, color: status.fg }}
    >
      {quant ? '정량' : '서술'}
    </span>
  )
}

function Tag({ children }: { children: string }) {
  return (
    <span className="w-fit rounded bg-ai-soft px-1.5 py-px text-[11px] font-semibold text-ai">
      {children}
    </span>
  )
}
