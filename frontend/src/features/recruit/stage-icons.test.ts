import { describe, expect, it } from 'vitest'
import { resolvedStageIcon } from '@/features/recruit/stage-icons'

describe('전형 기본 아이콘', () => {
  it('기존 전형은 기본값을 사용하고 HR의 명시적 선택을 우선한다', () => {
    expect(resolvedStageIcon('DOCUMENT', null, '서류 접수')).toBe('FILE_TEXT')
    expect(resolvedStageIcon('ASSESSMENT', null, '코딩테스트')).toBe('CODE')
    expect(resolvedStageIcon('INTERVIEW', null, '실무면접')).toBe('CHAIR')
    expect(resolvedStageIcon('ASSESSMENT', null, '채용검진')).toBe('HEALTH')
    expect(resolvedStageIcon('INTERVIEW', 'USERS', '실무면접')).toBe('USERS')
    expect(resolvedStageIcon('INTERVIEW', 'NONE', '실무면접')).toBe('NONE')
  })
})
