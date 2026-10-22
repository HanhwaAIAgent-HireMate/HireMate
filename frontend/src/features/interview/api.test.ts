import { describe, expect, it } from 'vitest'

import { finishedPreparing } from '@/features/interview/api'

describe('finishedPreparing', () => {
  it('질문을 만드는 중이었다가 끝났을 때만 카드 질문을 다시 불러온다', () => {
    expect(finishedPreparing({ preparing: true }, { preparing: false })).toBe(true)
    expect(finishedPreparing({ preparing: true }, { preparing: true })).toBe(false)
    expect(finishedPreparing({ preparing: false }, { preparing: false })).toBe(false)
    expect(finishedPreparing(undefined, { preparing: false })).toBe(false)
  })
})
