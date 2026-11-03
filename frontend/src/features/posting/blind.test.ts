import { describe, expect, it } from 'vitest'

import { blindLineNumbers } from './blind'

describe('blindLineNumbers', () => {
  it('학력 · 출신 학교 조건이 들어간 줄만 고른다', () => {
    const lines = [
      '컴퓨터공학 전공 또는 관련 학과 졸업',
      '4년제 대학교 졸업자',
      '석사 이상 우대',
      'SKY 출신 우대',
      '정보처리기사 자격증 보유',
      'Java 기반 서버 개발 경험',
    ]

    expect(blindLineNumbers(lines)).toEqual([2, 3, 4])
  })

  it('여대 · 여고는 학교가 아니라 성별 조건이라 여기서 보지 않는다 (늘 막는 조건)', () => {
    expect(blindLineNumbers(['여대 출신'])).toEqual([])
  })
})
