import type { PostingContent, PostingFocus } from '@/features/posting/api'

/** HR이 골라 AI에게 맡길 수 있는 본문 칸. 회사 소개는 칸 전체를, 나머지는 목록의 줄 하나를 고른다 */
export type FocusField = 'intro' | 'duties' | 'qualifications' | 'preferred' | 'benefits'

/** 공고 편집 화면에서 고른 줄. index는 화면에 보이는 줄 순서(0부터)이고 회사 소개는 없다 */
export type LineFocus = { field: FocusField; index?: number }

const LABELS: Record<FocusField, string> = {
  intro: '회사 소개',
  duties: '주요 업무',
  qualifications: '자격 요건',
  preferred: '우대 사항',
  benefits: '복지',
}

/** 입력칸 위에 보여 줄 이름 (예: 우대 사항 3번) */
export function focusLabel(focus: LineFocus) {
  return focus.index === undefined
    ? LABELS[focus.field]
    : `${LABELS[focus.field]} ${focus.index + 1}번`
}

/** 고를 수 있는 줄인지. 빈 줄은 저장할 때 빠지므로 고를 수 없다 */
export function hasLine(focus: LineFocus, content: PostingContent) {
  if (focus.field === 'intro') return true
  return focus.index !== undefined && Boolean(content[focus.field][focus.index]?.trim())
}

/** 서버에 보낼 고른 줄. 서버는 빈 줄을 뺀 목록을 쓰므로, 고른 줄 앞의 빈 줄은 세지 않는다 */
export function toServerFocus(focus: LineFocus, content: PostingContent): PostingFocus {
  if (focus.field === 'intro' || focus.index === undefined)
    return { field: focus.field, index: null }
  const before = content[focus.field].slice(0, focus.index)
  return { field: focus.field, index: before.filter((line) => line.trim()).length }
}
