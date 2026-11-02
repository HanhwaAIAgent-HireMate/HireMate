import { describe, expect, it } from 'vitest'

import { followLines } from './required'

describe('필수 표시 따라가기', () => {
  const before = ['Java 3년 이상', '학사 이상', 'RDBMS 경험']

  it('줄 순서만 바뀌면 표시를 그대로 둔다', () => {
    expect(
      followLines(['학사 이상'], before, ['학사 이상', 'Java 3년 이상', 'RDBMS 경험']),
    ).toEqual(['학사 이상'])
  })

  it('한 줄만 고치면 고친 글로 표시를 옮긴다', () => {
    expect(
      followLines(['Java 3년 이상'], before, ['Java 5년 이상', '학사 이상', 'RDBMS 경험']),
    ).toEqual(['Java 5년 이상'])
  })

  it('줄을 지우면 지운 줄의 표시만 뺀다', () => {
    expect(
      followLines(['Java 3년 이상', '학사 이상'], before, ['Java 3년 이상', 'RDBMS 경험']),
    ).toEqual(['Java 3년 이상'])
  })
})
