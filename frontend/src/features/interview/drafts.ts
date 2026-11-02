import { useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'

import { meQueryKey, type Member } from '@/lib/auth'

export type InterviewDraft = { text: string; version: number; savedAt: number }
const PREFIX = 'hiremate:interview-draft:'
const MAX_AGE = 7 * 24 * 60 * 60 * 1000

/** 기업과 계정별로 구분해 다른 면접관의 초안을 복구하지 않는다. */
export function useInterviewDraftKey(stage: string, application: string, field: string) {
  const client = useQueryClient()
  const member = client.getQueryData<Member | null>(meQueryKey)
  const companyId = member?.companyId
  const memberId = member?.memberId
  useEffect(() => {
    if (companyId && memberId) removeSharedNoteDrafts(companyId, memberId)
  }, [companyId, memberId])
  return member
    ? `${PREFIX}${member.companyId}:${member.memberId}:${stage}:${application}:${field}`
    : null
}

/** 제거된 공유 기록 초안만 정리한다. 개인 메모와 답변 초안은 유지한다. */
export function removeSharedNoteDrafts(companyId: string, memberId: string) {
  const prefix = `${PREFIX}${companyId}:${memberId}:`
  try {
    const keys = Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index))
    for (const key of keys) {
      if (key?.startsWith(prefix) && key.endsWith(':shared-note')) localStorage.removeItem(key)
    }
  } catch {
    // 브라우저 저장소 접근이 제한돼도 현재 답변과 개인 메모 편집은 계속한다.
  }
}

export function readDraft(key: string | null): InterviewDraft | null {
  if (!key) return null
  try {
    const value: unknown = JSON.parse(localStorage.getItem(key) ?? 'null')
    if (
      typeof value !== 'object' ||
      value === null ||
      !('text' in value) ||
      typeof value.text !== 'string' ||
      value.text.length > 100_000 ||
      !('version' in value) ||
      typeof value.version !== 'number' ||
      !Number.isSafeInteger(value.version) ||
      value.version < 0 ||
      !('savedAt' in value) ||
      typeof value.savedAt !== 'number' ||
      Date.now() - value.savedAt > MAX_AGE
    )
      return null
    return value as InterviewDraft
  } catch {
    return null
  }
}

export function writeDraft(key: string | null, text: string, version: number): boolean {
  if (!key) return false
  try {
    localStorage.setItem(key, JSON.stringify({ text, version, savedAt: Date.now() }))
    return true
  } catch {
    return false
  }
}

/** 이전 저장 요청이 새로 입력한 초안을 삭제하지 않게 한다. */
export function clearDraft(key: string | null, text: string) {
  if (!key) return
  try {
    if (readDraft(key)?.text === text) localStorage.removeItem(key)
  } catch {
    /* 저장소를 사용할 수 없어도 입력 내용은 화면에 남긴다. */
  }
}
