export type DiffPart = { kind: 'same' | 'removed' | 'added'; text: string }

function sentences(text: string) {
  return text.split(/(?<=[.!?。])\s+/).filter((sentence) => sentence.length > 0)
}

/** 문장 단위로 바뀐 부분을 찾는다. 지운 문장은 취소선, 새 문장은 초록으로 보여 준다. */
export function sentenceDiff(before: string, after: string): DiffPart[] {
  const a = sentences(before)
  const b = sentences(after)
  const table = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i--) {
    for (let j = b.length - 1; j >= 0; j--) {
      table[i][j] =
        a[i] === b[j] ? table[i + 1][j + 1] + 1 : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  const parts: DiffPart[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      parts.push({ kind: 'same', text: a[i] })
      i++
      j++
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      parts.push({ kind: 'removed', text: a[i++] })
    } else {
      parts.push({ kind: 'added', text: b[j++] })
    }
  }
  while (i < a.length) parts.push({ kind: 'removed', text: a[i++] })
  while (j < b.length) parts.push({ kind: 'added', text: b[j++] })
  return parts
}
