/** 단계 문구를 쌓는다. 같은 문구가 이어지면 한 번만 남긴다 (ai 서버가 대화 기록에 남기는 방식과 같다). */
export function addStep(steps: string[], text: string): string[] {
  return steps[steps.length - 1] === text ? steps : [...steps, text]
}

/** 걸린 시간 표시. 1분이 넘으면 분과 초로 쓴다. */
export function durationLabel(seconds: number): string {
  if (seconds < 60) return `${seconds}초`
  const rest = seconds % 60
  return rest ? `${Math.floor(seconds / 60)}분 ${rest}초` : `${Math.floor(seconds / 60)}분`
}
