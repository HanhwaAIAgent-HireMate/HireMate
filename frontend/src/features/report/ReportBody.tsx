import { cn } from 'cn'
import { useMemo, type ReactNode } from 'react'

import { chartFor, CHART_TYPES, peopleColors, type ChartContext } from './charts'
import {
  crossCounts,
  evidenceParts,
  isScoreView,
  meterOf,
  POSITIVE,
  SCORE_CELLS,
  topPercent,
  type EvidenceParts,
  type Meter,
} from './derive'
import { EChart } from './EChart'
import { SEQ, STATUS, word } from './palette'
import { NO_NAMES, usePrinting, useShownNames, whoOf, withNames } from './people'
import type { Block, ReportBundle, ReportView } from './types'

/** 부품이 6칸 격자에서 차지하는 칸. 줄이 남으면 그 줄 마지막 부품을 늘린다 */
const SPAN: Record<string, number> = {
  distribution: 4,
  donut: 2,
  cross: 2,
  share: 4,
  stacked: 3,
  bar: 3,
  radar: 2,
}

const SPAN_CLASS: Record<number, string> = {
  2: 'md:col-span-2',
  3: 'md:col-span-3',
  4: 'md:col-span-4',
  5: 'md:col-span-5',
  6: 'md:col-span-6',
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

/** 부품이 그리는 데 쓰는 것. 문장 속 지원자번호에 이름을 붙이는 text와 인쇄 중인지(printing)를 더한다 */
interface BodyContext extends ChartContext {
  text: (value: string) => string
  printing: boolean
}

/**
 * 리포트 본문. 설계서(spec)의 섹션과 부품을 묶음(bundle) 값으로 그린다.
 * 웹에서는 backend가 붙여 준 names로 '이름(지원자번호)'를 보여 주고, 인쇄(PDF)할 때는 지원자번호만 보여 준다
 */
export function ReportBody({ report }: { report: ReportView }) {
  const { bundle, spec } = report
  const printing = usePrinting()
  const names = printing ? NO_NAMES : report.names
  const ctx = useMemo<BodyContext>(
    () => ({
      bundle,
      name: (number) => names[number] ?? null,
      who: (number) => whoOf(names, number),
      color: peopleColors(bundle.targets),
      text: (value) => withNames(value, names),
      printing,
    }),
    [bundle, names, printing],
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
        {ctx.text(spec.summary)}
      </p>
      {spec.sections.map((section, index) => (
        <section key={index} className="flex flex-col gap-2.5" aria-label={ctx.text(section.title)}>
          <div className="flex items-center gap-2.5">
            <span className="rounded-md bg-ai-soft px-1.5 py-0.5 text-xs font-bold text-ai tabular-nums">
              {String(index + 1).padStart(2, '0')}
            </span>
            <h3 className="text-base font-bold">{ctx.text(section.title)}</h3>
            {section.area && (
              <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                영역
              </span>
            )}
          </div>
          <p className="text-sm leading-6 font-semibold text-foreground/90">
            {ctx.text(section.takeaway)}
          </p>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-6">
            {pack(section.blocks).map((span, i) => (
              <div
                key={i}
                className={cn('min-w-0 rounded-xl border bg-card px-4 py-3.5', SPAN_CLASS[span])}
              >
                <BlockView block={section.blocks[i]} ctx={ctx} />
              </div>
            ))}
          </div>
        </section>
      ))}
      <p className="text-center text-xs text-muted-foreground">
        이 리포트는 확정된 전형 결과를 요약할 뿐, 합격 · 불합격 결정을 바꾸지 않아요.
      </p>
    </div>
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

function Head({ title, caption }: { title: string; caption?: string }) {
  return (
    <div className="mb-2.5">
      <div className="text-[13.5px] font-bold">{title}</div>
      {caption && <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">{caption}</p>}
    </div>
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
  const head = <Head title={title} caption={caption && ctx.text(caption)} />
  if (chart) {
    return (
      <>
        {head}
        <EChart option={chart.option} height={chart.height} label={title} still={ctx.printing} />
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
          <div className="text-[13.5px] font-bold">{title}</div>
          {caption && (
            <p className="mt-0.5 text-[12.5px] leading-5 text-muted-foreground">
              {ctx.text(caption)}
            </p>
          )}
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
  return (
    <div className="flex flex-col gap-3">
      {order.map((number) => (
        <div
          key={number}
          className="flex flex-col gap-2 rounded-r-lg border-l-4 bg-muted/40 px-4 py-3 text-[13px] leading-6"
          style={{ borderLeftColor: ctx.color(number) ?? '#C9CED6' }}
        >
          <Person number={number} ctx={ctx} />
          <div className="flex flex-col divide-y divide-dashed">
            {(grouped.get(number) ?? []).map((item, i) => (
              <EvidenceEntry key={i} item={item} bundle={bundle} ctx={ctx} />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function EvidenceEntry({
  item,
  bundle,
  ctx,
}: {
  item: EvidenceBlock['items'][number]
  bundle: ReportBundle
  ctx: BodyContext
}) {
  const parts = item.evidence.flatMap((id) => {
    const found = bundle.evidence.find((evidence) => evidence.id === id)
    return found ? [evidenceParts(bundle, found)] : []
  })
  const quotes = [
    ...new Map(parts.flatMap((p) => (p.quote ? [[p.quote, p] as const] : []))).values(),
  ]
  const keywords = item.keywords ?? []
  return (
    <div className="flex flex-col gap-2 py-3 first:pt-1 last:pb-0">
      {keywords.length > 0 ? (
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag>키워드</Tag>
          {keywords.map((keyword) => (
            <span key={keyword} className="rounded-md border bg-card px-2 py-px font-semibold">
              {ctx.text(keyword)}
            </span>
          ))}
        </div>
      ) : (
        item.text && <div className="font-semibold">{ctx.text(item.text)}</div>
      )}
      {parts.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {keywords.length > 0 && item.text && `${ctx.text(item.text)} · `}
          근거 문장 없음 · 다음 전형에서 확인
        </p>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <Tag>AI 분석</Tag>
            {parts.map((part) => (
              <Analysis key={part.id} part={part} />
            ))}
          </div>
          {quotes.length > 0 && (
            <div className="flex flex-col gap-1">
              <Tag>원문</Tag>
              {quotes.map((part) => (
                <p key={part.id} className="text-[12.5px] text-muted-foreground">
                  <span className="text-foreground">“{part.quote}”</span> · {part.source}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** 분석 Agent의 판단 하나. 어느 항목의 판단인지(영역 · 항목 · 판정)를 위에 붙인다 */
function Analysis({ part }: { part: EvidenceParts }) {
  const status = part.verdict ? STATUS[part.verdict] : undefined
  return (
    <div className="flex flex-col gap-0.5">
      {(part.label || status) && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {part.area && <span className="text-muted-foreground">{part.area}</span>}
          {part.label && <b>{part.label}</b>}
          {status && (
            <span
              className="rounded px-1.5 py-px font-semibold"
              style={{ background: status.bg, color: status.fg }}
            >
              {status.icon} {status.label}
            </span>
          )}
        </div>
      )}
      <p>
        {part.analysis}{' '}
        <span className="text-xs text-muted-foreground">· {AGENTS[part.agent] ?? part.agent}</span>
      </p>
    </div>
  )
}

function Tag({ children }: { children: string }) {
  return (
    <span className="w-fit rounded bg-ai-soft px-1.5 py-px text-[11px] font-semibold text-ai">
      {children}
    </span>
  )
}
