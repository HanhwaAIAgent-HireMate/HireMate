import { useCallback, useRef } from 'react'

export type RegisterAnswerSave = (flush: () => Promise<void>) => () => void

/** 종료 전에 현재 초안과 이미 시작한 저장을 모두 기다린다. 필터로 숨긴 답변의 저장도 포함한다. */
export function usePendingAnswerSaves() {
  const saves = useRef(new Set<{ flush: () => Promise<void> }>())
  const register = useCallback<RegisterAnswerSave>((flush) => {
    const entry = { flush }
    saves.current.add(entry)
    return () => {
      // 질문이 숨겨져도 저장을 마칠 때까지 보관하고, 실패하면 종료 전에 다시 확인한다.
      void flush().then(
        () => saves.current.delete(entry),
        () => {},
      )
    }
  }, [])
  const flush = useCallback(async () => {
    const results = await Promise.allSettled([...saves.current].map((save) => save.flush()))
    const failed = results.find((result) => result.status === 'rejected')
    if (failed?.status === 'rejected') throw failed.reason
  }, [])
  return { register, flush }
}
