import { describe, expect, it } from 'vitest'

import { cn } from './utils'

describe('cn', () => {
  it('충돌하는 Tailwind 클래스는 뒤에 온 것만 남긴다', () => {
    expect(cn('px-2 py-1', 'px-4')).toBe('py-1 px-4')
  })
})
