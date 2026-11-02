import { beforeEach, expect, it, vi } from 'vitest'
import { clearDraft, readDraft, writeDraft } from './drafts'

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
})

it('이전 저장 응답이 새 초안을 삭제하지 않는다', () => {
  writeDraft('key', '새 초안', 2)
  clearDraft('key', '이전 초안')
  expect(readDraft('key')?.text).toBe('새 초안')
  clearDraft('key', '새 초안')
  expect(readDraft('key')).toBeNull()
})

it('손상됐거나 만료된 초안과 잘못된 버전은 복구하지 않는다', () => {
  localStorage.setItem('key', '{invalid')
  expect(readDraft('key')).toBeNull()
  localStorage.setItem('key', JSON.stringify({ text: 'old', version: 1, savedAt: 0 }))
  expect(readDraft('key')).toBeNull()
  localStorage.setItem('key', JSON.stringify({ text: 'bad', version: -0.1, savedAt: Date.now() }))
  expect(readDraft('key')).toBeNull()
})

it('브라우저 저장소가 제한돼도 예외 대신 실패 여부를 반환한다', () => {
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('quota')
  })
  expect(writeDraft('key', 'draft', 0)).toBe(false)
})
