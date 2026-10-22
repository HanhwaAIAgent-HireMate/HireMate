import { describe, expect, it } from 'vitest'

import { previewReceipt } from './receipt'

describe('previewReceipt', () => {
  it('회사명과 공고명은 이 공고 값, 지원자 값은 예시로 채운다', () => {
    expect(
      previewReceipt(
        '{지원자명}님, {회사명} {공고명} 지원번호 {지원번호}번',
        '한빛소프트',
        '백엔드 개발자',
      ),
    ).toBe('홍길동님, 한빛소프트 백엔드 개발자 지원번호 1번')
  })

  it('같은 변수가 여러 번 나와도 모두 바꾸고, 공고명이 비어 있으면 자리 이름을 보여 준다', () => {
    expect(previewReceipt('[{회사명}] {공고명} · {회사명}', 'A사', '')).toBe('[A사] 공고명 · A사')
  })
})
