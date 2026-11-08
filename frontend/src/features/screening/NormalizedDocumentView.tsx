import { Code2, ImageIcon } from 'lucide-react'
import { createContext, useContext, useMemo, type ReactNode } from 'react'

import {
  codeBlocks,
  codeLabel,
  slot,
  visualSubject,
  type Block,
  type ListItem,
  type NormalizedDocument,
  type SlotKey,
  type Span,
  type TableBlock,
} from '@/features/screening/normalized'
import { locate } from '@/features/screening/evidence'

type View = {
  spans: Map<SlotKey, Span[]>
  metric: string
  /** 그리지 않고 '어떤 코드인지'만 알릴 코드 문단 */
  code: Set<string>
  /** 코드와 짝인 '줄바꿈 · 들여쓰기는 원본 PDF에서' 안내. 코드 안내에 합쳐 따로 보이지 않는다 */
  notices: Set<string>
}

const ViewContext = createContext<View>({
  spans: new Map(),
  metric: '',
  code: new Set(),
  notices: new Set(),
})

/**
 * 정제 문서(서류 원문)를 그대로 그린다. 맨 위 주제(구역)는 칸으로 나누고, 문단 · 목록 · 표는 각각 문단 · 글머리표 · 표로
 * 보인다. 글은 JSON에 있는 그대로 쓰고 고치거나 빼지 않는다 (모델을 다시 부르지 않는다). 쪽이 바뀌는 곳에 쪽 번호를 단다.
 * 코드는 그리지 않고 어떤 코드인지만 알리고, 그림 · 차트는 자료 이름만 알린다 (둘 다 원본 PDF에 있다).
 * spans를 주면 근거 자리에 밑줄을 긋고, 밑줄 안의 지표(metric)는 굵게 한다.
 */
export function NormalizedDocumentView({
  document,
  spans = new Map(),
  metric = '',
}: {
  document: NormalizedDocument
  spans?: Map<SlotKey, Span[]>
  metric?: string
}) {
  const { code, notices } = useMemo(() => codeBlocks(document), [document])
  return (
    <ViewContext.Provider value={{ spans, metric, code, notices }}>
      <div className="space-y-3 text-[13px] leading-6">
        {document.document.title && (
          <p className="text-base font-bold">
            <Text slotKey="document:title" text={document.document.title} />
          </p>
        )}
        <PagedBlocks blocks={document.blocks} />
      </div>
    </ViewContext.Provider>
  )
}

/** 맨 위 블록을 칸으로 그리며 쪽이 넘어가는 곳에 '2쪽' 구분선을 넣는다 */
function PagedBlocks({ blocks }: { blocks: Block[] }) {
  const { notices } = useContext(ViewContext)
  const shown: { block: Block; first: number; turned: boolean }[] = []
  let page = 1
  for (const block of blocks) {
    if (notices.has(block.id)) continue
    const first = Math.min(...block.pages)
    const turned = Number.isFinite(first) && first > page
    if (turned) page = first
    shown.push({ block, first, turned })
  }
  return shown.map(({ block, first, turned }) => {
    return (
      <div key={block.id} className="space-y-3">
        {turned && (
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            <span className="h-px flex-1 bg-border" />
            {first}쪽
            <span className="h-px flex-1 bg-border" />
          </div>
        )}
        {block.type === 'section' ? <TopicCard block={block} /> : <BlockView block={block} />}
      </div>
    )
  })
}

/** 맨 위 주제 하나를 칸으로 묶는다. 제목은 칸 머리에 둔다 */
function TopicCard({ block }: { block: Extract<Block, { type: 'section' }> }) {
  return (
    <section className="overflow-hidden rounded-lg border">
      {block.title && (
        <h4 className="border-b bg-muted/40 px-3 py-1.5 text-sm font-semibold">
          <Text slotKey={slot.title(block.id)} text={block.title} />
        </h4>
      )}
      <div className="space-y-2 px-3 py-2.5">
        <Children blocks={block.blocks} />
      </div>
    </section>
  )
}

function Children({ blocks }: { blocks: Block[] }) {
  const { notices } = useContext(ViewContext)
  return blocks
    .filter((block) => !notices.has(block.id))
    .map((block) => <BlockView key={block.id} block={block} />)
}

function BlockView({ block }: { block: Block }) {
  const { code, spans } = useContext(ViewContext)
  switch (block.type) {
    case 'section':
      // 주제 안의 소주제: 왼쪽 선으로 묶는다
      return (
        <section className="space-y-1.5 border-l-2 border-muted pl-3">
          {block.title && (
            <h5 className="font-semibold">
              <Text slotKey={slot.title(block.id)} text={block.title} />
            </h5>
          )}
          <Children blocks={block.blocks} />
        </section>
      )
    case 'paragraph': {
      if (code.has(block.id)) {
        const { kind, note } = codeLabel(block.text)
        const label = `코드 · ${kind}${note ? ` — ${note}` : ''}`
        // 근거가 코드 안에 있으면 코드 글 대신 이 안내에 밑줄을 긋는다
        const cited = (spans.get(slot.text(block.id)) ?? []).length > 0
        return (
          <Notice icon={<Code2 className="mt-0.5 size-3.5 shrink-0" aria-hidden />}>
            {cited ? <mark className={MARK}>{label} (근거가 이 코드 안에 있어요)</mark> : label}
          </Notice>
        )
      }
      return (
        <p className="whitespace-pre-wrap">
          <Text slotKey={slot.text(block.id)} text={block.text} />
        </p>
      )
    }
    case 'list':
      return <Items items={block.items} />
    case 'table':
      return <Table block={block} />
    case 'visual_notice':
      return (
        <Notice icon={<ImageIcon className="mt-0.5 size-3.5 shrink-0" aria-hidden />}>
          {VISUAL_LABELS[block.visualType] ?? '시각 자료'} · {visualSubject(block.message)}
        </Notice>
      )
  }
}

const MARK =
  'rounded-sm bg-ai/10 text-inherit underline decoration-ai decoration-2 underline-offset-4'

const VISUAL_LABELS: Record<string, string> = {
  image: '이미지',
  chart: '차트',
  diagram: '도식',
  unknown: '시각 자료',
}

function Notice({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <p className="flex items-start gap-1.5 rounded-md bg-muted/60 px-2.5 py-1.5 text-xs text-muted-foreground">
      {icon}
      <span>{children}</span>
    </p>
  )
}

function Items({ items }: { items: ListItem[] }) {
  return (
    <ul className="list-disc space-y-0.5 pl-5 marker:text-muted-foreground">
      {items.map((item) => (
        <li key={item.id} className="whitespace-pre-wrap">
          <Text slotKey={slot.text(item.id)} text={item.text} />
          {item.items.length > 0 && <Items items={item.items} />}
        </li>
      ))}
    </ul>
  )
}

function Table({ block }: { block: TableBlock }) {
  return (
    <div className="space-y-1">
      {block.title && (
        <p className="text-xs font-medium text-muted-foreground">
          <Text slotKey={slot.title(block.id)} text={block.title} />
        </p>
      )}
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-left">
          {block.headers.length > 0 && (
            <thead className="bg-muted/60 text-xs text-muted-foreground">
              <tr>
                {block.headers.map((header, column) => (
                  <th key={column} className="px-3 py-1.5 font-medium">
                    <Text slotKey={slot.header(block.id, column)} text={header} />
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {block.rows.map((row, index) => (
              <tr key={index} className="border-t align-top first:border-t-0">
                {row.map((cell, column) => (
                  <td key={column} className="px-3 py-1.5 whitespace-pre-wrap">
                    <Text slotKey={slot.cell(block.id, index, column)} text={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

/** 칸 하나의 글. 근거 자리에 밑줄을 긋는다 */
function Text({ slotKey, text }: { slotKey: SlotKey; text: string }) {
  const { spans, metric } = useContext(ViewContext)
  const marks = spans.get(slotKey)
  if (!marks || marks.length === 0) return text
  const parts: ReactNode[] = []
  let cursor = 0
  for (const span of marks) {
    if (span.start > cursor) parts.push(text.slice(cursor, span.start))
    parts.push(
      <mark key={span.start} className={MARK}>
        {bold(text.slice(span.start, span.end), metric)}
      </mark>,
    )
    cursor = span.end
  }
  if (cursor < text.length) parts.push(text.slice(cursor))
  return parts
}

function bold(text: string, metric: string): ReactNode {
  const core = metric.replace(/\s*\([^)]*\)\s*$/, '')
  const found = core ? locate(text, core) : null
  if (!found) return text
  return (
    <>
      {text.slice(0, found.index)}
      <strong>{text.slice(found.index, found.index + found.length)}</strong>
      {text.slice(found.index + found.length)}
    </>
  )
}
