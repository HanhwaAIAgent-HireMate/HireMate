/** 서류 필수 조건을 표시할 수 있는 목록 */
export type RequiredKey = 'qualifications' | 'preferred'
export const REQUIRED_KEYS: RequiredKey[] = ['qualifications', 'preferred']
export const isRequiredKey = (key: string): key is RequiredKey =>
  REQUIRED_KEYS.includes(key as RequiredKey)
/**
 * 줄이 바뀔 때 필수 표시를 따라가게 한다. 줄 순서만 바뀌면 그대로, 한 줄만 고치면 고친 글로 옮기고,
 * 줄을 더하거나 지우면 남은 줄의 표시만 둔다
 */
export function followLines(marked: string[], before: string[], after: string[]): string[] {
  if (before.length === after.length) {
    const edited = before.flatMap((line, index) => (line === after[index] ? [] : [index]))
    const reordered = [...before].sort().join('\n') === [...after].sort().join('\n')
    if (edited.length === 1 && !reordered) {
      const index = edited[0]
      return marked.map((line) => (line === before[index] ? after[index] : line))
    }
  }
  return marked.filter((line) => after.includes(line))
}
