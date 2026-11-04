import { describe, expect, it } from 'vitest'

import { withRo } from './format'

describe('withRo', () => {
  it.each([
    ['직무역량 평가', '직무역량 평가로'], // 받침 없음
    ['최종 면접', '최종 면접으로'], // 받침 있음 (TC IV-11)
    ['1차 면접', '1차 면접으로'],
    ['서류 전형', '서류 전형으로'],
    ['개발 과제', '개발 과제로'],
    ['실무 평가실', '실무 평가실로'], // ㄹ 받침은 '로'
    ['Round 2', 'Round 2(으)로'], // 한글로 끝나지 않으면 알 수 없다
  ])('%s → %s', (word, expected) => {
    expect(withRo(word)).toBe(expected)
  })
})
