/**
 * 정제 문서(서류 원문) 타입과 근거 밑줄 자리 찾기. backend apply.NormalizedDocument와 같은 모양이다.
 * 생성된 API 타입은 블록 종류를 클래스 이름(Section · Listing …)으로 적어 실제 JSON(type: section · list …)과 달라 여기서 쓴다.
 */

type Pages = { pages: number[] }

export type ListItem = Pages & { id: string; text: string; items: ListItem[] }

export type SectionBlock = Pages & {
  id: string
  type: 'section'
  title: string | null
  blocks: Block[]
}
export type ParagraphBlock = Pages & { id: string; type: 'paragraph'; text: string }
export type ListBlock = Pages & { id: string; type: 'list'; items: ListItem[] }
export type TableBlock = Pages & {
  id: string
  type: 'table'
  title: string | null
  headers: string[]
  rows: string[][]
}
export type VisualNoticeBlock = Pages & {
  id: string
  type: 'visual_notice'
  visualType: 'image' | 'chart' | 'diagram' | 'unknown'
  message: string
}
export type Block = SectionBlock | ParagraphBlock | ListBlock | TableBlock | VisualNoticeBlock

export type NormalizedDocument = {
  schemaVersion: string
  document: { id: string; type: string; title: string | null; pageCount: number }
  blocks: Block[]
}

/** 지원자 카드의 정제 문서 목록에서 한 서류의 정제 문서. 정제 전이거나 실패했으면 없다 */
export function normalizedOf(
  list: { type: string; document: unknown }[] | undefined,
  type: string,
): NormalizedDocument | undefined {
  return list?.find((item) => item.type === type)?.document as NormalizedDocument | undefined
}

/** 화면에 글로 보이는 칸 하나의 열쇠. 같은 열쇠로 밑줄 자리를 찾아 그린다 */
export type SlotKey = string

export const slot = {
  title: (id: string) => `${id}:title`,
  text: (id: string) => `${id}:text`,
  header: (id: string, column: number) => `${id}:h${column}`,
  cell: (id: string, row: number, column: number) => `${id}:r${row}c${column}`,
}

/**
 * 코드 블록과 그 짝 안내문. 정제 정책은 코드를 줄바꿈 · 들여쓰기를 살린 paragraph에 담고 바로 뒤에 '줄바꿈과 들여쓰기는
 * 원본 PDF에서 확인' visual_notice(unknown)를 둔다. 그 짝을 코드로 보고, 짝이 없어도 줄 대부분이 코드처럼 생긴 여러 줄
 * 문단은 코드로 본다. 화면은 코드를 그리지 않고 어떤 코드인지만 알린다 (원본은 PDF에 있다).
 */
export function codeBlocks(document: NormalizedDocument): {
  code: Set<string>
  notices: Set<string>
} {
  const code = new Set<string>()
  const notices = new Set<string>()
  const walk = (blocks: Block[]) => {
    blocks.forEach((block, index) => {
      if (block.type === 'section') walk(block.blocks)
      if (block.type !== 'paragraph') return
      const next = blocks[index + 1]
      if (next && isCodeNotice(next)) {
        code.add(block.id)
        notices.add(next.id)
      } else if (looksLikeCode(block.text)) {
        code.add(block.id)
      }
    })
  }
  walk(document.blocks)
  return { code, notices }
}

function isCodeNotice(block: Block) {
  return (
    block.type === 'visual_notice' &&
    block.visualType === 'unknown' &&
    /줄바꿈|들여쓰기/.test(block.message)
  )
}

const CODE_LINE =
  /[{};]\s*$|^\s*(@\w+|public |private |protected |def |class |import |from \S+ import|SELECT |CREATE |ALTER |INSERT |UPDATE |git |docker |cd |npm |yarn |pip |\.\/|#|--|\/\/|[├└│])/i

function looksLikeCode(text: string) {
  const lines = text.split('\n').filter((line) => line.trim())
  return (
    lines.length >= 3 && lines.filter((line) => CODE_LINE.test(line)).length / lines.length >= 0.6
  )
}

/**
 * 코드가 무엇인지: 종류(Java 코드 · SQL · 폴더 구조 …)와, 첫 줄이 설명 주석이면 그 설명. 실행 명령어 · 폴더 구조의 첫 줄
 * 주석은 '1. 인프라 실행' 같은 단계 이름이라 설명으로 쓰지 않는다.
 */
export function codeLabel(text: string): { kind: string; note: string } {
  const kind = codeKind(text)
  const first = text.split('\n').find((line) => line.trim()) ?? ''
  const comment = /^\s*(?:\/\/|--|#)\s*(.+)$/.exec(first)
  const describes = comment && !/^!/.test(comment[1]) && !/실행 명령어|폴더 구조/.test(kind)
  return { kind, note: describes ? comment[1].trim() : '' }
}

const COMMAND = /^\s*(git |docker |cd |npm |yarn |pip |\.\/gradlew|java -jar|k6 |cp |curl )/m

function codeKind(text: string) {
  const tree =
    /[├└│]/.test(text) || text.split('\n').filter((line) => /\/\s*$/.test(line)).length >= 2
  if (tree && COMMAND.test(text)) return '실행 명령어 · 폴더 구조'
  if (tree) return '폴더 구조'
  if (COMMAND.test(text)) return '실행 명령어'
  if (/\b(SELECT|CREATE (TABLE|INDEX)|ALTER TABLE|INSERT INTO|UPDATE \w+ SET)\b/i.test(text))
    return /\b(public|private|class)\b/.test(text) ? 'Java 코드' : 'SQL'
  if (/\bredis\.call\b|\bipairs\b|\bend\s*$/m.test(text) && !/[{;]/.test(text))
    return 'Lua 스크립트'
  if (/^\s*(def |from \S+ import|import \w+$)|@\w+\.task\b/m.test(text)) return 'Python 코드'
  if (
    /\b(public|private|protected)\b.*[({]|@(Service|Component|Repository|Transactional)\b/.test(
      text,
    )
  )
    return 'Java 코드'
  if (/\b(const|let|function)\b|=>|\binterface \w+ \{/.test(text))
    return 'JavaScript · TypeScript 코드'
  if (/^\s*[\w.-]+:\s*$/m.test(text)) return '설정 파일'
  return '코드'
}

/**
 * 시각 자료 안내에서 자료 이름만 남긴다. 모델이 쓴 안내는 '‘구성도’ 자료는 텍스트로 확인할 수 없습니다. 원본 PDF에서
 * 확인해 주세요.'처럼 길어, 따옴표 안 이름을 쓰고 없으면 '~자료' · '~을 확인' 앞까지를 쓴다. 못 줄이면 그대로 둔다.
 */
export function visualSubject(message: string): string {
  const quoted = /[‘'“"]([^’'”"]+)[’'”"]/.exec(message)
  if (quoted) return `‘${quoted[1].trim()}’`
  const sentence = message.split(/(?<=[.!?])\s/)[0]
  const cut = sentence.search(
    /(?:[을를]\s*(?:나타내는|보여\s*주는|보여주는))|\s*(?:시각\s*)?자료|[을를]\s*확인|[은는의]\s*원본/,
  )
  const subject = (cut > 0 ? sentence.slice(0, cut) : '').trim()
  return subject && subject.length <= 60 ? subject : message
}

/**
 * 문서에 보이는 글을 읽는 순서대로 칸마다 늘어놓는다 (안내문 visual_notice는 뺀다). 코드 문단도 넣어 근거 자리를 찾는다:
 * 화면은 코드를 그리지 않지만, 근거가 코드 안에 있으면 그 코드 안내에 밑줄을 긋는다.
 */
export function slots(document: NormalizedDocument): { key: SlotKey; text: string }[] {
  const found: { key: SlotKey; text: string }[] = []
  if (document.document.title) found.push({ key: 'document:title', text: document.document.title })
  const items = (list: ListItem[]) => {
    for (const item of list) {
      found.push({ key: slot.text(item.id), text: item.text })
      items(item.items)
    }
  }
  const walk = (blocks: Block[]) => {
    for (const block of blocks) {
      if (block.type === 'section') {
        if (block.title) found.push({ key: slot.title(block.id), text: block.title })
        walk(block.blocks)
      } else if (block.type === 'paragraph') {
        found.push({ key: slot.text(block.id), text: block.text })
      } else if (block.type === 'list') {
        items(block.items)
      } else if (block.type === 'table') {
        if (block.title) found.push({ key: slot.title(block.id), text: block.title })
        block.headers.forEach((text, column) =>
          found.push({ key: slot.header(block.id, column), text }),
        )
        block.rows.forEach((row, index) =>
          row.forEach((text, column) =>
            found.push({ key: slot.cell(block.id, index, column), text }),
          ),
        )
      }
    }
  }
  walk(document.blocks)
  return found
}

export type Span = { start: number; end: number }

/**
 * 근거 문장의 밑줄 자리를 칸마다 찾는다. 근거는 PDF에서 읽은 글에서 왔고 정제 문서는 줄바꿈 · 띄어쓰기 · 가운뎃점을
 * 정리했으므로, 글자 · 숫자만 남겨 맞춘다 (칸을 넘어 이어지는 문장도 찾는다). 그래도 못 찾으면 낱말이 대부분 겹치는
 * 칸 하나에 밑줄을 긋고, 그마저 없으면 unmatched로 돌려 화면이 따로 보여 준다.
 */
export function matchEvidence(
  document: NormalizedDocument,
  sentences: string[],
): { spans: Map<SlotKey, Span[]>; unmatched: string[] } {
  const list = slots(document)
  // 글자 · 숫자만 남긴 문서 전체와, 그 글자마다 원래 칸 · 자리
  let compact = ''
  const origin: { slot: number; index: number }[] = []
  list.forEach((item, slotIndex) => {
    for (let index = 0; index < item.text.length; index++) {
      const char = item.text[index]
      if (WORD.test(char)) {
        compact += char.toLowerCase()
        origin.push({ slot: slotIndex, index })
      }
    }
  })
  const spans = new Map<SlotKey, Span[]>()
  const add = (slotIndex: number, span: Span) => {
    const key = list[slotIndex].key
    spans.set(key, [...(spans.get(key) ?? []), span])
  }
  const unmatched: string[] = []
  for (const sentence of sentences) {
    const needle = squash(sentence)
    const at = needle ? compact.indexOf(needle) : -1
    if (at >= 0) {
      // 칸마다 첫 글자 ~ 마지막 글자를 밑줄로 묶는다
      const touched = new Map<number, Span>()
      for (let index = at; index < at + needle.length; index++) {
        const { slot: slotIndex, index: position } = origin[index]
        const span = touched.get(slotIndex)
        if (span) span.end = position + 1
        else touched.set(slotIndex, { start: position, end: position + 1 })
      }
      touched.forEach((span, slotIndex) => add(slotIndex, span))
      continue
    }
    const best = closest(list, sentence)
    if (best !== null) add(best, { start: 0, end: list[best].text.length })
    else unmatched.push(sentence)
  }
  spans.forEach((value, key) => spans.set(key, merge(value)))
  return { spans, unmatched }
}

const WORD = /[\p{L}\p{N}]/u

function squash(text: string) {
  return Array.from(text)
    .filter((char) => WORD.test(char))
    .join('')
    .toLowerCase()
}

/** 근거 낱말의 70% 이상이 들어 있는 칸 가운데 가장 많이 겹치는 칸. 낱말이 셋보다 적으면 찾지 않는다 */
function closest(list: { text: string }[], sentence: string): number | null {
  const words = sentence
    .split(/[^\p{L}\p{N}]+/u)
    .map((word) => word.toLowerCase())
    .filter((word) => word.length >= 2)
  if (words.length < 3) return null
  let best: { index: number; ratio: number } | null = null
  list.forEach((item, index) => {
    const text = squash(item.text)
    const ratio = words.filter((word) => text.includes(word)).length / words.length
    if (ratio >= 0.7 && (!best || ratio > best.ratio)) best = { index, ratio }
  })
  return best === null ? null : (best as { index: number; ratio: number }).index
}

function merge(spans: Span[]): Span[] {
  const sorted = [...spans].sort((a, b) => a.start - b.start)
  const merged: Span[] = []
  for (const span of sorted) {
    const last = merged.at(-1)
    if (last && span.start <= last.end) last.end = Math.max(last.end, span.end)
    else merged.push({ ...span })
  }
  return merged
}
