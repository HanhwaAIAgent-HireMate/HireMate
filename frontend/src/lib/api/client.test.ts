import { describe, expect, it } from 'vitest'

import { ApiError, errorMessage, needsAdmin } from './client'

describe('errorMessage', () => {
  it('AI 서버 오류는 다시 시도와 계속될 때 할 일을 함께 알려 준다 (QA CM-08)', () => {
    const message = errorMessage(new ApiError(502, 'AI_UNAVAILABLE', ''))
    expect(message).toContain('다시 시도')
    expect(message).toContain('관리자')
  })

  it('접수 기간이 아닌 공고에 지원하면 그 이유를 알려 준다', () => {
    expect(errorMessage(new ApiError(409, 'POSTING_NOT_OPEN', ''))).toContain('접수 기간')
  })

  it('모르는 오류는 일반 문구를 쓴다', () => {
    expect(errorMessage(new ApiError(500, 'SOMETHING_NEW', ''))).toBe(
      '요청을 처리하지 못했어요. 잠시 후 다시 시도해 주세요.',
    )
  })
})

describe('needsAdmin', () => {
  it('AI 서버 · 서버 오류에만 관리자 확인 요청 버튼을 붙인다', () => {
    expect(needsAdmin(new ApiError(502, 'AI_UNAVAILABLE', ''))).toBe(true)
    expect(needsAdmin(new ApiError(500, 'INTERNAL_ERROR', ''))).toBe(true)
    expect(needsAdmin(new ApiError(409, 'POSTING_NOT_OPEN', ''))).toBe(false)
    expect(needsAdmin(new Error('network'))).toBe(false)
  })
})
