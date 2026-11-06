import type { CandidateDetail } from '@/features/screening/api'

export type DocumentType = CandidateDetail['documents'][number]['type']

/** 판정 근거 한 문장. 인재상 근거처럼 문서 종류를 모르면 서류에서 찾는다 */
export type EvidenceQuote = { document: DocumentType | null; sentence: string }

export type EvidenceGroup = { type: DocumentType; text: string; sentences: string[] }

/** 근거 문장을 서류별로 묶는다. 서류 원문에 있는 문장만 남기고, 문서 종류를 모르면 원문에서 찾는다 */
export function groupByDocument(
  quotes: EvidenceQuote[],
  documents: CandidateDetail['documents'],
): EvidenceGroup[] {
  const groups: EvidenceGroup[] = []
  for (const quote of quotes) {
    const found = documents.find(
      (document) =>
        document.text &&
        (quote.document === null || document.type === quote.document) &&
        locate(document.text, quote.sentence),
    )
    if (!found?.text) continue
    let group = groups.find((item) => item.type === found.type)
    if (!group) {
      group = { type: found.type, text: found.text, sentences: [] }
      groups.push(group)
    }
    if (!group.sentences.includes(quote.sentence)) group.sentences.push(quote.sentence)
  }
  return groups
}

/** 원문에서 문장의 자리. PDF에서 읽은 글은 줄바꿈 · 띄어쓰기가 다를 수 있어 공백 차이는 무시한다 */
export function locate(text: string, sentence: string): { index: number; length: number } | null {
  const words = sentence.split(/\s+/).filter(Boolean)
  if (words.length === 0) return null
  const escaped = words.map((word) => word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const match = new RegExp(escaped.join('\\s*')).exec(text)
  return match ? { index: match.index, length: match[0].length } : null
}

/**
 * 원문에서 밑줄을 칠 구간. 근거 문장이 겹치거나 공백만 사이에 두고 이어지면 한 구간으로 합친다
 * (화면에 밑줄 하나로 보이는 것을 한 개로 센다).
 */
export function underlineSpans(
  text: string,
  sentences: string[],
): { index: number; length: number }[] {
  const spans = sentences
    .map((sentence) => locate(text, sentence))
    .filter((span): span is { index: number; length: number } => span !== null)
    .sort((a, b) => a.index - b.index)
  const merged: { index: number; end: number }[] = []
  for (const span of spans) {
    const last = merged.at(-1)
    const end = span.index + span.length
    if (last && (span.index <= last.end || text.slice(last.end, span.index).trim() === '')) {
      last.end = Math.max(last.end, end)
    } else {
      merged.push({ index: span.index, end })
    }
  }
  return merged.map((span) => ({ index: span.index, length: span.end - span.index }))
}
