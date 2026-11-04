import { useEffect, useState } from 'react'

function sameShape(value: unknown, sample: unknown): boolean {
  if (sample === null)
    return value === null || ['number', 'string', 'boolean'].includes(typeof value)
  if (Array.isArray(sample))
    return (
      Array.isArray(value) && value.every((item) => !sample.length || sameShape(item, sample[0]))
    )
  if (typeof sample === 'object')
    return (
      typeof value === 'object' &&
      value !== null &&
      Object.entries(sample).every(([key, item]) =>
        sameShape((value as Record<string, unknown>)[key], item),
      )
    )
  return typeof value === typeof sample
}

/** 같은 탭·공고의 미저장 편집을 복구한다. 서버 내용이 달라졌으면 이전 편집으로 덮어쓰지 않는다. */
export function usePostingRecovery<T>(key: string, saved: T, enabled = true, warnOnLeave = true) {
  const storageKey = `hiremate:posting:${key}`
  const baseline = JSON.stringify(saved)
  const [recovery] = useState<{ value: T } | null>(() => {
    if (!enabled) return null
    try {
      const raw = sessionStorage.getItem(storageKey)
      if (!raw || raw.length > 1_000_000) return null
      const cached = JSON.parse(raw) as { baseline?: string; value?: unknown }
      return cached.baseline === baseline && sameShape(cached.value, saved)
        ? { value: cached.value as T }
        : null
    } catch {
      return null
    }
  })
  const [value, setValue] = useState<T>(() => recovery?.value ?? saved)
  const dirty = enabled && JSON.stringify(value) !== baseline
  useEffect(() => {
    try {
      if (dirty) sessionStorage.setItem(storageKey, JSON.stringify({ baseline, value }))
      else sessionStorage.removeItem(storageKey)
    } catch {
      // 저장소가 제한된 브라우저에서는 이탈 경고로 편집 내용을 보호한다.
    }
  }, [baseline, dirty, storageKey, value])
  useEffect(() => {
    if (!dirty || !warnOnLeave) return
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [dirty, warnOnLeave])
  return { value, setValue, dirty, restored: Boolean(recovery) }
}
