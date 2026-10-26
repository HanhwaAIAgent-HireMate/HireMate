import { describe, expect, it } from 'vitest'

import { moveStage, stagesProblem, type StageForm } from './stages'

const stages: StageForm[] = [
  { name: '서류 전형', type: 'DOCUMENT' },
  { name: '코딩테스트', type: 'ASSESSMENT' },
  { name: '1차 면접', type: 'INTERVIEW' },
]

describe('전형 절차 직접 편집', () => {
  it('앞뒤로 옮기고, 끝을 넘으면 그대로 둔다', () => {
    expect(moveStage(stages, 2, -1).map((stage) => stage.name)).toEqual([
      '서류 전형',
      '1차 면접',
      '코딩테스트',
    ])
    expect(moveStage(stages, 0, -1)).toBe(stages)
    expect(moveStage(stages, 2, 1)).toBe(stages)
  })

  it('전형은 1개에서 10개까지, 이름이 있고 서로 달라야 저장한다', () => {
    expect(stagesProblem(stages)).toBeNull()
    expect(stagesProblem([])).toContain('하나 이상')
    expect(
      stagesProblem(Array.from({ length: 11 }, (_, i) => ({ ...stages[0], name: `${i}` }))),
    ).toContain('10개')
    expect(stagesProblem([...stages, { name: ' ', type: 'INTERVIEW' }])).toContain('이름이 없는')
    expect(stagesProblem([...stages, { name: ' 1차 면접 ', type: 'INTERVIEW' }])).toContain(
      '이름이 같은',
    )
  })
})
