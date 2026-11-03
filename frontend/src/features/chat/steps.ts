import type { Schemas } from '@/lib/api/client'

/**
 * 처리 단계 하나. depth 0은 Root의 단계, 1은 그 아래에서 부른 도구나 하위 Agent의 일, 2는 그 일의 결과다.
 * 문구는 코드가 정한 문장이고 지원자 이름과 개수만 채워져 온다.
 */
export type ChatStep = Schemas['ChatStatus']

/** 단계 트리의 한 마디. index는 받은 순서다 */
export type StepNode = { step: ChatStep; index: number; children: StepNode[] }

/** 단계를 쌓는다. 같은 깊이의 같은 문구가 이어지면 한 번만 남긴다 (ai 서버가 대화 기록에 남기는 방식과 같다). */
export function addStep(steps: ChatStep[], step: ChatStep): ChatStep[] {
  const last = steps.at(-1)
  return last && last.text === step.text && last.depth === step.depth ? steps : [...steps, step]
}

/**
 * 받은 순서의 단계를 깊이로 묶는다. 단계는 앞에 온 더 얕은 단계의 아래에 들어간다.
 * 위 단계 없이 깊은 단계가 먼저 오면 맨 위에 둔다.
 */
export function stepTree(steps: ChatStep[]): StepNode[] {
  const roots: StepNode[] = []
  const open: StepNode[] = []
  steps.forEach((step, index) => {
    const node: StepNode = { step, index, children: [] }
    while (open.length && (open.at(-1)?.step.depth ?? 0) >= step.depth) open.pop()
    const parent = open.at(-1)
    if (parent) parent.children.push(node)
    else roots.push(node)
    open.push(node)
  })
  return roots
}

/** Root 단계 수. 답의 '처리 과정 N단계'는 Root 단계만 센다 */
export function rootStepCount(steps: ChatStep[]): number {
  return stepTree(steps).length
}

/** 걸린 시간 표시. 1분이 넘으면 분과 초로 쓴다. */
export function durationLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}초`
  const rest = seconds % 60
  return rest ? `${Math.floor(seconds / 60)}분 ${rest}초` : `${Math.floor(seconds / 60)}분`
}
