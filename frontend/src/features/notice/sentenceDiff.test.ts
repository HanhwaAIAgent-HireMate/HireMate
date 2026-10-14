import { describe, expect, it } from 'vitest'

import { sentenceDiff } from './sentenceDiff'

describe('sentenceDiff', () => {
  it('바뀐 문장만 지움과 추가로 나눈다', () => {
    const parts = sentenceDiff(
      '첫 문장입니다. 둘째 문장입니다. 셋째입니다.',
      '첫 문장입니다. 새 둘째 문장입니다. 셋째입니다.',
    )

    expect(parts).toEqual([
      { kind: 'same', text: '첫 문장입니다.' },
      { kind: 'removed', text: '둘째 문장입니다.' },
      { kind: 'added', text: '새 둘째 문장입니다.' },
      { kind: 'same', text: '셋째입니다.' },
    ])
  })
})
