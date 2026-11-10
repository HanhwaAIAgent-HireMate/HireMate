import { useStageInterviewProgress } from '@/features/interview/live'
import type { AssignedInterview, InterviewerWorkspace } from '@/features/interview/sessions'
import type { StageOverview } from '@/features/screening/api'
import { useStageUi } from '@/features/screening/store'
import { useCandidateTable, type TableFeature } from '@/features/screening/table'

/** 빈 대화에 보여 주는 추천 질문 수 */
const LIMIT = 3
/** 이보다 긴 열 이름은 키워드를 만들지 못해 원래 문장을 그대로 쓴 것이라 질문에 넣지 않는다 */
const LABEL_MAX = 20
/** 한 번에 비교할 만한 지원자 수 */
const COMPARE_MAX = 5
/** 면접을 마친 사람의 답변을 서류와 견준다. 범위를 스스로 정해 '미결정 N명 중'을 앞에 붙이지 않는다 */
const ANSWERS_VS_DOCUMENTS = '면접을 마친 지원자 중 답변이 서류 내용과 다른 사람 있어?'

export type SuggestionInput = Pick<StageOverview, 'type' | 'status' | 'counts' | 'hasScores'> & {
  /** 공고의 자격요건 · 우대사항 · 인재상 열. 서류 전형에서만 쓴다 */
  features: Pick<TableFeature, 'group' | 'label'>[]
  /** Chat 입력창에 멘션한 지원자 수 */
  mentions: number
  /** 목록에서 체크한 지원자 수 */
  checked: number
  /** 면접을 마친 지원자 수. 면접 전형에서만 쓴다 */
  interviewed: number
}

/**
 * 빈 대화의 추천 질문. 전형 상태, 결정 현황, 공고 기준과 지금 고른 지원자로 정한다.
 * 모델을 부르지 않고 코드가 문장을 고르므로 차별 조건이나 근거 없는 내용이 들어가지 않는다.
 */
export function suggestQuestions(input: SuggestionInput): string[] {
  const { counts } = input
  if (counts.total === 0) return []
  const picks: string[] = []
  const target = targetQuestion(input)
  if (target) picks.push(target)

  // 결과를 확정한 전형은 선택 지원자를 바꿀 수 없어 찾기 대신 결과를 돌아본다
  if (input.status !== 'ACTIVE') {
    picks.push('이번 전형 결과 리포트 보여줘')
    if (counts.pending > 0) picks.push(`미결정으로 남은 ${counts.pending}명은 어떤 지원자야?`)
    return picks.slice(0, LIMIT)
  }

  // 모두 결정했으면 확정 전에 결과를 돌아본다
  if (counts.pending === 0) picks.push('이번 전형 결과 리포트 보여줘')
  // 결정을 시작한 뒤에는 남은 미결정 지원자 가운데서 찾는다
  const within =
    counts.pending > 0 && counts.pending < counts.total ? `미결정 ${counts.pending}명 중 ` : ''
  const finds = stageFinds(input)
  if (finds.length > 0 && finds[0] !== ANSWERS_VS_DOCUMENTS) finds[0] = within + finds[0]
  picks.push(...finds)
  return picks.slice(0, LIMIT)
}

/** 멘션하거나 체크한 지원자에 대한 질문. 멘션이 이번 질문에 붙는 대상이라 체크보다 먼저다 */
function targetQuestion({ type, status, mentions, checked }: SuggestionInput): string | null {
  const [who, count] = mentions > 0 ? ['멘션한', mentions] : ['체크한', checked]
  if (count === 0 || count > COMPARE_MAX) return null
  if (count > 1) return `${who} 지원자 ${count}명을 비교해줘`
  if (type === 'INTERVIEW' && status === 'ACTIVE')
    return `${who} 지원자에게 물어볼 면접 질문 만들어줘`
  return `${who} 지원자의 강점과 확인할 점을 정리해줘`
}

/** 진행 중인 전형에서 지원자를 찾는 질문. 전형 종류와 쌓인 자료에 맞춘다 */
function stageFinds({ type, hasScores, features, interviewed }: SuggestionInput): string[] {
  switch (type) {
    case 'DOCUMENT': {
      const finds: string[] = []
      const preference = features.find(
        (feature) => feature.group === 'PREFERENCE' && feature.label.length <= LABEL_MAX,
      )
      if (preference) finds.push(`우대사항 '${preference.label}'에 해당하는 지원자 찾아줘`)
      if (features.some((feature) => feature.group === 'QUALIFICATION'))
        finds.push('자격요건을 모두 충족한 지원자 찾아줘')
      if (features.some((feature) => feature.group === 'TALENT'))
        finds.push('인재상이 잘 드러나는 지원자 찾아줘')
      return finds
    }
    case 'ASSESSMENT':
      return hasScores
        ? [
            '평가 점수가 높은 지원자 5명 찾아줘',
            '평가 점수는 높은데 서류 내용과 차이가 큰 지원자 있어?',
          ]
        : ['평가 결과가 아직 없는 지원자 보여줘']
    // 면접 전형에는 점수가 없다. 면접 전에는 서류에서 역할을 확인할 사람을, 면접 뒤에는 답변과 서류의 차이를 찾는다
    case 'INTERVIEW':
      return [
        ...(interviewed > 0 ? [ANSWERS_VS_DOCUMENTS] : []),
        '서류에서 팀 성과와 본인 역할이 구분되지 않는 지원자 찾아줘',
      ]
  }
}

/** HR 전형 화면 Chat의 추천 질문. 공고 기준 열은 서류 전형에서만, 면접 진행 현황은 면접 전형에서만 불러온다 */
export function useStageSuggestions(overview: StageOverview): string[] {
  const document = overview.type === 'DOCUMENT'
  const interview = overview.type === 'INTERVIEW'
  const table = useCandidateTable(overview.stageId, document)
  const progress = useStageInterviewProgress(overview.stageId, interview)
  const mentions = useStageUi((state) => state.mentions.length)
  const checked = useStageUi((state) => state.checked.length)
  return suggestQuestions({
    type: overview.type,
    status: overview.status,
    counts: overview.counts,
    hasScores: overview.hasScores,
    features: document ? (table.data?.features ?? []) : [],
    mentions,
    checked,
    interviewed: interview
      ? (progress.data ?? []).filter((session) => session.status === 'ENDED').length
      : 0,
  })
}

export type InterviewerSuggestionInput = {
  /** 면접 화면에 연 지원자 이름 */
  name: string
  status: AssignedInterview['status']
  /** 이번 면접에 기록한 답변이 있는가 */
  answered: boolean
  /** 앞 면접 전형에 기록한 답변이 있는가 */
  previousAnswered: boolean
}

/**
 * 면접관 Chat의 추천 질문. 면접관 화면은 지금 연 지원자를 멘션하지 않으므로 '이 지원자' 대신 이름으로 가리키고,
 * 면접 전, 진행 중, 종료 뒤에 맞춰 고른다. 선택 지원자는 바꿀 수 없어 찾기 대신 분석 · 질문을 권한다.
 */
export function suggestInterviewerQuestions({
  name,
  status,
  answered,
  previousAnswered,
}: InterviewerSuggestionInput): string[] {
  const who = `${name} 님`
  switch (status) {
    case 'SCHEDULED':
      return [
        `${who}의 서류에서 면접 때 확인할 점을 정리해줘`,
        ...(previousAnswered ? [`${who}의 이전 면접에서 확인하지 못한 점을 정리해줘`] : []),
        `${who}에게 물어볼 면접 질문 만들어줘`,
      ].slice(0, LIMIT)
    case 'IN_PROGRESS':
      return [
        ...(answered ? [`${who}의 지금까지 답변에서 더 확인할 점을 알려줘`] : []),
        `${who}이 프로젝트에서 본인이 한 일을 정리해줘`,
        `${who}의 본인 역할을 확인할 질문 하나 더 만들어줘`,
      ].slice(0, LIMIT)
    case 'ENDED':
      return [
        ...(answered ? [`${who}의 면접 답변을 서류 내용과 비교해줘`] : []),
        `${who}의 강점과 더 확인이 필요한 점을 정리해줘`,
      ]
    case 'ABSENT':
      // 면접에 오지 않았으니 서류로만 정리한다
      return [`${who}의 서류에서 강점과 확인할 점을 정리해줘`]
  }
}

/** 면접관 화면의 추천 질문. 면접 기록을 받기 전에는 목록의 면접 상태로 고른다 */
export function interviewerSuggestions(
  interview: Pick<AssignedInterview, 'applicantName' | 'status'>,
  workspace: InterviewerWorkspace | undefined,
): string[] {
  return suggestInterviewerQuestions({
    name: interview.applicantName,
    status: workspace?.session.status ?? interview.status,
    answered: (workspace?.questions ?? []).some((access) => access.question.answer.trim() !== ''),
    previousAnswered: (workspace?.previous ?? []).some((previous) =>
      previous.questions.some((question) => question.answer.trim() !== ''),
    ),
  })
}
