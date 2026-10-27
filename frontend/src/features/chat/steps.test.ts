import { describe, expect, it } from 'vitest'

import { addStep, durationLabel } from './steps'

describe('처리 단계 문구', () => {
  it('단계를 순서대로 쌓고 이어진 같은 문구만 한 번으로 남긴다', () => {
    let steps: string[] = []
    for (const text of ['확인', '확인', '찾기', '확인']) steps = addStep(steps, text)

    expect(steps).toEqual(['확인', '찾기', '확인'])
  })

  it('걸린 시간은 1분이 넘으면 분과 초로 쓴다', () => {
    expect(durationLabel(8)).toBe('8초')
    expect(durationLabel(60)).toBe('1분')
    expect(durationLabel(75)).toBe('1분 15초')
  })
})
