import { describe, expect, it } from 'vitest'
import { resolvedStageIcon } from '@/features/recruit/stage-icons'

describe('전형 기본 아이콘', () => {
  it.each(['2차면접', '2차 면접', '최종면접', '최종 면접', '2차면접(최종면접)'])(
    '%s은 사람 아이콘을 사용하고 명시적인 변경은 유지한다',
    (name) => {
      expect(resolvedStageIcon('INTERVIEW', 'AUTO', name)).toBe('USERS')
      expect(resolvedStageIcon('INTERVIEW', 'VIDEO', name)).toBe('VIDEO')
    },
  )

  it('1차면접은 기존 대화 아이콘을 유지한다', () => {
    expect(resolvedStageIcon('INTERVIEW', 'AUTO', '1차면접')).toBe('MESSAGES')
  })

  it('기존 전형은 기본값을 사용하고 HR의 명시적 선택을 우선한다', () => {
    expect(resolvedStageIcon('DOCUMENT', null, '서류 접수')).toBe('FILE_TEXT')
    expect(resolvedStageIcon('ASSESSMENT', null, '코딩테스트')).toBe('CODE')
    expect(resolvedStageIcon('INTERVIEW', null, '실무면접')).toBe('CHAIR')
    expect(resolvedStageIcon('ASSESSMENT', null, '채용검진')).toBe('HEALTH')
    expect(resolvedStageIcon('INTERVIEW', 'USERS', '실무면접')).toBe('USERS')
    expect(resolvedStageIcon('INTERVIEW', 'NONE', '실무면접')).toBe('NONE')
  })
})
