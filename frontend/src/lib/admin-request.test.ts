import { toast } from 'sonner'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ADMIN_REQUEST_LABEL, requestAdmin, toastAiError } from '@/lib/admin-request'
import { ApiError } from '@/lib/api/client'

vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }))

describe('AI 오류 토스트', () => {
  afterEach(() => vi.clearAllMocks())

  it('AI 서버 오류면 토스트에 [관리자에게 확인 요청]을 붙이고, 닫을 때까지 둔다', () => {
    toastAiError(new ApiError(502, 'AI_UNAVAILABLE', ''))

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('관리자'), {
      action: { label: ADMIN_REQUEST_LABEL, onClick: requestAdmin },
      duration: Infinity,
      closeButton: true,
    })
  })

  it('입력 오류처럼 관리자가 필요 없는 오류는 문구만 보인다', () => {
    toastAiError(new ApiError(409, 'POSTING_NOT_OPEN', ''))

    expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('접수 기간'))
  })

  it('관리자 확인 요청을 누르면 보냈다고 알린다', () => {
    requestAdmin()

    expect(toast.success).toHaveBeenCalledWith('관리자에게 확인 요청을 보냈어요.')
  })
})
