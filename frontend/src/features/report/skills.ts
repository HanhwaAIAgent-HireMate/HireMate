/** Report Agent가 읽은 지침(스킬) 이름을 담당자가 읽는 말로. ai `report/skills/*.md`의 name과 같다 */
const SKILL_LABELS: Record<string, string> = {
  'visual-guide': '그래프 고르기',
  compare: '지원자 비교',
  evidence: '근거 고르기',
  final: '채용 최종 리포트',
  'stage-document': '서류 전형 결과',
  'stage-assessment': '평가 전형 결과',
  'stage-interview': '면접 전형 결과',
}

export function skillLabel(name: string) {
  return SKILL_LABELS[name] ?? name
}
