import { useEffect, useState } from 'react'

/** 다 쓰기 전에는 이 비율을 넘지 않는다. 실제로 끝나야 100%다 */
const MAX_BEFORE_DONE = 95

/**
 * 쓰는 중 리포트의 어림 진행률(%)과 남은 시간(초).
 * Report Agent는 단계별 진행을 알리지 않아, 이 기업에서 같은 종류 리포트가 보통 걸린 시간에 견줘 어림한다
 */
export function useReportProgress(
  createdAt: string | undefined,
  expectedSeconds: number | undefined,
) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])
  if (!createdAt || !expectedSeconds) return null
  const elapsed = Math.max(0, (now - Date.parse(createdAt)) / 1000)
  return {
    percent: Math.min(MAX_BEFORE_DONE, Math.round((elapsed / expectedSeconds) * 100)),
    remaining: Math.max(0, Math.round(expectedSeconds - elapsed)),
  }
}

/** 진행률과 남은 시간 한 줄 */
export function progressLabel(progress: { percent: number; remaining: number }) {
  return progress.remaining > 0
    ? `약 ${progress.percent}% · 남은 시간 약 ${progress.remaining}초`
    : `약 ${progress.percent}% · 마무리하는 중이에요`
}
