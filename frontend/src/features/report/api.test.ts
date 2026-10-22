import { describe, expect, it } from 'vitest'

import { reportNotReady } from '@/features/report/api'
import { ApiError } from '@/lib/api/client'

describe('reportNotReady', () => {
  it('리포트를 쓰는 중일 때만 다시 불러온다', () => {
    expect(reportNotReady(new ApiError(404, 'REPORT_NOT_READY', ''))).toBe(true)
    expect(reportNotReady(new ApiError(404, 'RECRUITMENT_NOT_FOUND', ''))).toBe(false)
    expect(reportNotReady(new Error('network'))).toBe(false)
  })
})
