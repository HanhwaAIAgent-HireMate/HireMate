import { describe, expect, it } from 'vitest'

import { addStep, durationLabel, rootStepCount, stepTree, type ChatStep } from './steps'

const step = (text: string, depth = 0): ChatStep => ({ text, depth })

describe('처리 단계 문구', () => {
  it('단계를 순서대로 쌓고 이어진 같은 깊이의 같은 문구만 한 번으로 남긴다', () => {
    let steps: ChatStep[] = []
    for (const next of [step('확인'), step('확인'), step('확인', 1), step('찾기'), step('확인')])
      steps = addStep(steps, next)

    expect(steps).toEqual([step('확인'), step('확인', 1), step('찾기'), step('확인')])
  })

  it('하위 단계는 앞에 온 더 얕은 단계 아래로 묶는다', () => {
    const tree = stepTree([
      step('요청을 확인하고 있어요'),
      step('요청에 맞는 답변을 준비하고 있어요'),
      step('정유민의 프로필을 읽고 있어요', 1),
      step('서류 Agent · 정유민의 제출 문서 2건을 검토하고 있어요', 1),
      step('근거 문장 3개를 찾았어요', 2),
      step('답변의 근거를 검토하고 있어요'),
      step('항목 2개 중 근거 확인 2개', 1),
    ])

    expect(tree.map((node) => node.step.text)).toEqual([
      '요청을 확인하고 있어요',
      '요청에 맞는 답변을 준비하고 있어요',
      '답변의 근거를 검토하고 있어요',
    ])
    expect(tree[1].children.map((node) => node.index)).toEqual([2, 3])
    expect(tree[1].children[1].children.map((node) => node.step.text)).toEqual([
      '근거 문장 3개를 찾았어요',
    ])
    expect(tree[2].children.map((node) => node.index)).toEqual([6])
  })

  it('위 단계 없이 온 깊은 단계는 맨 위에 두고, 단계 수는 맨 위 단계만 센다', () => {
    const steps = [step('정유민의 프로필을 읽고 있어요', 1), step('요청을 확인하고 있어요')]
    expect(stepTree(steps).map((node) => node.index)).toEqual([0, 1])
    expect(rootStepCount([step('확인'), step('읽기', 1), step('검토')])).toBe(2)
  })

  it('걸린 시간은 1분이 넘으면 분과 초로 쓴다', () => {
    expect(durationLabel(8)).toBe('8초')
    expect(durationLabel(60)).toBe('1분')
    expect(durationLabel(75)).toBe('1분 15초')
  })
})
