import { afterEach, describe, expect, it, vi } from 'vitest'

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
  it('AI 서버 · 서버 오류에 관리자 확인 요청 버튼을 붙이고, 일반 오류에는 붙이지 않는다', () => {
    expect(needsAdmin(new ApiError(502, 'AI_UNAVAILABLE', ''))).toBe(true)
    expect(needsAdmin(new ApiError(500, 'INTERNAL_ERROR', ''))).toBe(true)
    expect(needsAdmin(new ApiError(409, 'POSTING_NOT_OPEN', ''))).toBe(false)
    expect(needsAdmin(new Error('network'))).toBe(false)
  })
})

describe('네트워크 오류', () => {
  afterEach(() => vi.restoreAllMocks())

  it('인터넷은 되는데 서버에 닿지 못하면 관리자 확인 요청을 붙인다', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true)
    const failed = new TypeError('Failed to fetch')

    expect(errorMessage(failed)).toContain('서버에 연결하지 못했어요')
    expect(needsAdmin(failed)).toBe(true)
    expect(needsAdmin(new ApiError(504, 'UNKNOWN', ''))).toBe(true)
    // 개발 중 Vite 프록시는 backend가 꺼져 있으면 본문 없이 500을 준다
    expect(needsAdmin(new ApiError(500, 'UNKNOWN', ''))).toBe(true)
  })

  it('내 인터넷이 끊겼으면 연결을 확인하라고 하고 관리자 요청은 붙이지 않는다', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false)
    const failed = new TypeError('Failed to fetch')

    expect(errorMessage(failed)).toContain('인터넷 연결이 끊겼어요')
    expect(needsAdmin(failed)).toBe(false)
  })
})
