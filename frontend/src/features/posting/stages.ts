import type { StageType } from '@/features/recruit/labels'

/** 공고 작성 화면에서 HR이 직접 고치는 전형 하나 */
export type StageForm = { name: string; type: StageType }

/** 전형 절차에 넣을 수 있는 전형 수 */
export const MAX_STAGES = 10

export function toStageForms(stages: StageForm[]): StageForm[] {
  return stages.map(({ name, type }) => ({ name, type }))
}

/** 저장할 수 없는 이유. 전형 안내가 이름으로 이어지기 때문에 같은 이름을 막는다 */
export function stagesProblem(stages: StageForm[]): string | null {
  if (stages.length === 0) return '전형을 하나 이상 넣어 주세요.'
  if (stages.length > MAX_STAGES) return `전형은 ${MAX_STAGES}개까지 넣을 수 있어요.`
  const names = stages.map((stage) => stage.name.trim())
  if (names.some((name) => !name)) return '이름이 없는 전형이 있어요. 전형을 눌러 이름을 써 주세요.'
  if (new Set(names).size < names.length) {
    return "이름이 같은 전형이 있어요. '1차 면접', '2차 면접'처럼 다르게 써 주세요."
  }
  return null
}

/** index의 전형을 delta만큼 옮긴다. 끝을 넘으면 그대로다 */
export function moveStage(stages: StageForm[], index: number, delta: number): StageForm[] {
  const target = index + delta
  if (target < 0 || target >= stages.length) return stages
  const next = [...stages]
  ;[next[index], next[target]] = [next[target], next[index]]
  return next
}
