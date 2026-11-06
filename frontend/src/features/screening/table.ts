import { useQueries, useQuery } from '@tanstack/react-query'

import {
  stageKeys,
  type CandidateAnalysis,
  type CandidateRow,
  type CriterionLine,
} from '@/features/screening/api'
import { api, unwrap, type Schemas } from '@/lib/api/client'

export type CandidateTable = Schemas['CandidateTable']
export type TableFeature = Schemas['Feature']
export type TalentFit = Schemas['TalentFit']
export type TalentMatch = Schemas['Match']

/**
 * 칸 표기. 조건형은 O · X, 경험형은 상 · 중 · 하다. 경험과 정량 지표가 함께 있으면 상, 경험만 있으면 중,
 * 하지 않았다고 적혀 있거나 서류에 관련 기록이 아예 없으면 하이고, 판정하지 못했으면 확인 필요다.
 * 인재상은 행동 확인 · 일부 확인 · 미확인이다
 */
export type Mark =
  | 'O'
  | 'X'
  | '상'
  | '중'
  | '하'
  | '행동 확인'
  | '일부 확인'
  | '미확인'
  | '확인 필요'
  | '분석 중'
  | '분석 실패'
export type Tone = 'good' | 'mid' | 'bad' | 'unknown' | 'waiting'

export type Cell = {
  mark: Mark
  tone: Tone
  /** 칸 아래 한 줄. 무엇을 했는지(경험의 차이)를 짧게 보여 준다 */
  note: string
  /** 마우스를 올리면 보여 주는 판정 이유 */
  detail: string
}

export const GROUP_LABELS: Record<TableFeature['group'], string> = {
  QUALIFICATION: '자격요건',
  PREFERENCE: '우대사항',
  TALENT: '인재상',
}

const WAITING: Cell = { mark: '분석 중', tone: 'waiting', note: '', detail: '' }
const TONES: Record<Mark, Tone> = {
  O: 'good',
  상: 'good',
  중: 'mid',
  X: 'bad',
  하: 'bad',
  '행동 확인': 'good',
  '일부 확인': 'mid',
  미확인: 'bad',
  '확인 필요': 'unknown',
  '분석 중': 'waiting',
  '분석 실패': 'unknown',
}

// O · 상은 붉은 계열, 중은 노란 계열, X · 하는 파란 계열로 한눈에 갈리게 한다. 붉은 글자는 눈이 덜 피로한 장미색으로 둔다.
// 표 보기와 지원자 카드의 AI 분석이 같은 색을 쓴다
export const TONE_CLASSES: Record<Tone, string> = {
  good: 'bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300',
  mid: 'bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300',
  bad: 'bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300',
  unknown: 'bg-muted text-muted-foreground',
  waiting: 'bg-muted/60 text-muted-foreground animate-pulse',
}

/** 표기의 색 */
export function markTone(mark: Mark): Tone {
  return TONES[mark]
}

/**
 * 항목 판정의 표기. 조건형은 충족이면 O, 아니면 X다. 경험형은 정량 지표가 있는 충족만 상이고,
 * 지표 없는 충족 · 부분 충족은 중, 미충족은 하다 (하지 않았다고 적혔든 관련 기록이 없든 같다).
 * 판정하지 못했으면 확인 필요다
 */
export function criterionMark(
  condition: boolean,
  line: Pick<CriterionLine, 'verdict' | 'metric'>,
): Mark {
  switch (line.verdict) {
    case 'MET':
      return condition ? 'O' : line.metric ? '상' : '중'
    case 'PARTIAL':
      return condition ? 'X' : '중'
    case 'NOT_MET':
      return condition ? 'X' : '하'
    default:
      return '확인 필요'
  }
}

const ANALYSIS_STALE_MS = 5 * 60 * 1000

/** 표 보기의 열 (자격요건 · 우대사항 · 인재상). 열 이름 키워드는 ai 서버가 한 번 만들고 다시 쓴다 */
export function useCandidateTable(stageId: string, enabled = true) {
  return useQuery({
    queryKey: ['stage', stageId, 'table'] as const,
    enabled,
    queryFn: () =>
      unwrap(api.GET('/api/stages/{stageId}/table', { params: { path: { stageId } } })),
    staleTime: ANALYSIS_STALE_MS,
  })
}

/** 지원자마다 카드의 AI 분석. 카드와 같은 키라 이미 연 지원자는 다시 받지 않는다 */
export function useTableAnalyses(stageId: string, rows: CandidateRow[]) {
  return useQueries({
    queries: rows.map((row) => ({
      queryKey: [...stageKeys.analysis(stageId, row.applicationId), row.analysisStatus],
      enabled: row.analysisStatus === 'DONE',
      queryFn: () =>
        unwrap(
          api.GET('/api/stages/{stageId}/candidates/{applicationId}/analysis', {
            params: { path: { stageId, applicationId: row.applicationId } },
          }),
        ),
      staleTime: ANALYSIS_STALE_MS,
    })),
  })
}

/** 지원자마다 인재상 판정. 처음 열 때만 Application Agent가 판정하고 그 뒤로는 저장된 판정이 온다 */
export function useTalentFits(stageId: string, rows: CandidateRow[], enabled: boolean) {
  return useQueries({
    queries: rows.map((row) => ({
      queryKey: ['stage', stageId, 'talents', row.applicationId, row.analysisStatus] as const,
      enabled: enabled && row.analysisStatus === 'DONE',
      queryFn: () =>
        unwrap(
          api.GET('/api/stages/{stageId}/candidates/{applicationId}/talents', {
            params: { path: { stageId, applicationId: row.applicationId } },
          }),
        ),
      staleTime: ANALYSIS_STALE_MS,
    })),
  })
}

/** 지원자 카드의 인재상 판정. 표 보기와 같은 캐시를 쓴다 */
export function useTalentFit(
  stageId: string,
  applicationId: string,
  status: CandidateRow['analysisStatus'],
) {
  return useQuery({
    queryKey: ['stage', stageId, 'talents', applicationId, status] as const,
    enabled: status === 'DONE',
    queryFn: () =>
      unwrap(
        api.GET('/api/stages/{stageId}/candidates/{applicationId}/talents', {
          params: { path: { stageId, applicationId } },
        }),
      ),
    staleTime: ANALYSIS_STALE_MS,
  })
}

function cell(mark: Mark, note: string, detail: string): Cell {
  return { mark, tone: TONES[mark], note, detail }
}

/** 자격요건 · 우대사항 칸. 접수 때 저장한 항목 판정을 표기로 옮긴다 (다시 판정하지 않는다) */
export function criterionCell(feature: TableFeature, line: CriterionLine | undefined): Cell {
  if (!line) return cell('확인 필요', '', '이 항목의 판정이 없어요.')
  const condition = feature.kind === 'CONDITION'
  const note =
    line.verdict === 'UNKNOWN'
      ? (line.unknownParts[0] ?? '')
      : line.verdict === 'NOT_MET'
        ? line.noRecord
          ? '서류에 해당 내용 없음'
          : (line.unsatisfiedParts[0] ?? '')
        : line.careerYears != null
          ? `관련 경력 ${line.careerYears}년`
          : line.metric || (line.satisfiedParts[0] ?? '')
  return cell(criterionMark(condition, line), note, line.reason)
}

export const TALENT_MARKS: Record<TalentMatch['level'], Mark> = {
  HIGH: '행동 확인',
  MID: '일부 확인',
  LOW: '미확인',
  UNKNOWN: '확인 필요',
}

/** 인재상 칸 */
export function talentCell(match: TalentMatch | undefined): Cell {
  if (!match) return cell('확인 필요', '', '인재상 판정이 없어요.')
  return cell(
    TALENT_MARKS[match.level],
    [match.evidence, match.metric].filter(Boolean).join(' · '),
    match.reason,
  )
}

/** 지원자 한 명의 칸들. 분석 중이면 모두 분석 중으로, 열의 순서대로 돌려준다 */
export function rowCells(
  row: CandidateRow,
  features: TableFeature[],
  analysis: CandidateAnalysis | undefined,
  talents: TalentFit | undefined,
): Cell[] {
  if (row.analysisStatus === 'FAILED') {
    return features.map(() =>
      cell('분석 실패', '', '서류 분석에 실패했어요. 카드에서 다시 분석할 수 있어요.'),
    )
  }
  const byId = new Map((analysis?.criteria ?? []).map((line) => [line.criterionId, line]))
  let talentIndex = 0
  return features.map((feature) => {
    if (feature.group === 'TALENT') {
      const index = talentIndex++
      return talents ? talentCell(talents.items[index]) : WAITING
    }
    return analysis ? criterionCell(feature, byId.get(feature.id)) : WAITING
  })
}

/** 확인할 점 카드 한 줄. mark가 없으면 항목 판정이 아닌 분석 알림이다 */
export type CheckPoint = {
  key: string
  label: string
  mark: Mark | null
  /** 카드 둘째 줄의 판정 요약 */
  summary: string
  /** 마우스를 올리면 보이는 전체 이유 */
  detail: string
  /** 담당자가 주의해서 볼 서류 신호 (잦은 이직, 기준 없는 수치, 서류 속 평가 지시문 등). 카드를 붉게 보인다 */
  warning?: boolean
}

const NO_RUBRIC_NOTE = '에 맞는 평가 기준이 없어'
const BLOCKED_NOTE = '채용 판단에 쓰면 안 되는 조건'
/** AI 초안이 고른 해석을 담당자가 확정하도록 알림 뒤에 붙인 문구 (ai rubric_draft.CONFIRM_MARK) */
const CONFIRM_MARK = ' 담당자 확인: '

/**
 * 확인할 점 카드: 지원자에게 더 확인할 것만 쓴다. 확인 필요인 항목과 채우지 못한 자격요건은 항목 이름과 판정 요약
 * 한 줄만 쓴다(번호 · 공고 문장 · 긴 이유는 뺀다). 판정 기준이 정하지 않아 갈린 항목(설정 검토만 있고 지원자에게 물을
 * 것이 없는 확인 필요)과 평가 기준 · 공고 문장 알림은 settingPoints로 따로 보인다
 */
export function checkPoints(
  analysis: Pick<CandidateAnalysis, 'criteria' | 'holds' | 'checks'>,
  labels: Map<string, string>,
): CheckPoint[] {
  const line = (item: CriterionLine, parts: string[]): CheckPoint => ({
    key: item.criterionId,
    label: labels.get(item.text) ?? item.text,
    mark: criterionMark(item.criterionType === 'CONDITION', item),
    // 요약이 없는 예전 분석은 빠진 부분, 그것도 없으면 판정 이유를 쓴다
    summary: item.brief || parts.join(' · ') || item.reason,
    detail: item.reason,
  })
  const unknown = analysis.criteria
    .filter(
      (item) => item.verdict === 'UNKNOWN' && !(item.settingNote && item.unknownParts.length === 0),
    )
    .map((item) => line(item, item.unknownParts))
  const short = analysis.criteria
    .filter(
      (item) =>
        item.category === 'QUALIFICATION' &&
        (item.verdict === 'NOT_MET' || item.verdict === 'PARTIAL'),
    )
    .map((item) => line(item, item.unsatisfiedParts))
  const notes = analysisNotes(analysis).filter(
    (note) => !note.text.includes(NO_RUBRIC_NOTE) && !note.text.includes(BLOCKED_NOTE),
  )
  const note = (item: (typeof notes)[number]): CheckPoint => ({
    key: item.text,
    label: item.title || (item.warning ? '주의' : '알림'),
    mark: null,
    summary: item.text,
    detail: item.text,
    warning: item.warning,
  })
  // 주의 신호를 맨 앞에 둔다
  const warnings = notes.filter((item) => item.warning).map(note)
  const others = notes.filter((item) => !item.warning).map(note)
  return [...warnings, ...unknown, ...short, ...others]
}

/**
 * 평가 설정 검토 카드: 지원자가 아니라 평가 기준을 담당자가 정해야 하는 점이다. 판정 기준이 정하지 않아 판정이 갈린
 * 항목(예: '대용량'의 규모 기준 없음), 채용 판단에 쓰면 안 되는 공고 조건, 평가 기준이 없어 AI 초안으로 판정한 알림
 */
export function settingPoints(
  analysis: Pick<CandidateAnalysis, 'criteria' | 'holds' | 'checks'>,
  labels: Map<string, string>,
): CheckPoint[] {
  const undecided: CheckPoint[] = analysis.criteria
    .filter((item) => item.settingNote)
    .map((item) => ({
      key: `setting-${item.criterionId}`,
      label: labels.get(item.text) ?? item.text,
      mark: null,
      summary: item.settingNote,
      detail: [item.brief, item.reason].filter(Boolean).join('\n'),
    }))
  const notes = analysisNotes(analysis).map((note) => note.text)
  const quoted = (text: string) => {
    const notice = text.split(CONFIRM_MARK)[0]
    return /'(.+)'/.exec(notice)?.[1] ?? notice
  }
  const blocked: CheckPoint[] = notes
    .filter((text) => text.includes(BLOCKED_NOTE))
    .map((text) => ({
      key: text,
      label: '평가 제외',
      mark: null,
      summary: quoted(text),
      detail: text,
    }))
  const noRubric = notes.filter((text) => text.includes(NO_RUBRIC_NOTE))
  const grouped: CheckPoint[] =
    noRubric.length > 0
      ? [
          {
            key: 'no-rubric',
            label: '평가 기준 없음',
            mark: null,
            summary: `공고 항목 ${noRubric.length}개는 AI가 만든 판정 기준 초안으로 판정`,
            detail: noRubric.map(quoted).join('\n'),
          },
        ]
      : []
  // 공고 문장만으로 정할 수 없어 AI 초안이 고른 해석: 담당자가 확정하거나 평가 기준을 저장해야 한다
  const interpretations: CheckPoint[] = noRubric
    .filter((text) => text.includes(CONFIRM_MARK))
    .map((text) => ({
      key: `confirm-${quoted(text)}`,
      label: labels.get(quoted(text)) ?? quoted(text),
      mark: null,
      summary: text.split(CONFIRM_MARK)[1],
      detail:
        'AI 판정 기준 초안이 고른 해석이에요. 평가 기준을 정해 저장하면 그 기준으로 다시 판정해요.',
    }))
  return [...undecided, ...blocked, ...interpretations, ...grouped]
}

/** 분석 알림. 항목 판정을 옮긴 문장("Q-01 '…': …")은 항목 카드와 겹치니 뺀다 */
function analysisNotes(
  analysis: Pick<CandidateAnalysis, 'criteria' | 'holds' | 'checks'>,
): { text: string; title: string; warning: boolean }[] {
  return [...analysis.holds, ...analysis.checks]
    .map((note) => ({ text: note.text, title: note.title ?? '', warning: note.warning ?? false }))
    .filter(
      (note) => !analysis.criteria.some((item) => note.text.startsWith(`${item.criterionId} '`)),
    )
}

/** 추가로 확인할 점 한두 개. 확인 필요 칸의 빠진 부분을 먼저, 없으면 확인 필요인 열 이름을 쓴다 */
export function followUps(features: TableFeature[], cells: Cell[], limit = 2): string[] {
  const unknown = cells
    .map((item, index) => ({ item, feature: features[index] }))
    .filter(({ item }) => item.mark === '확인 필요')
  const notes = unknown.map(({ item, feature }) => item.note || feature.label)
  return [...new Set(notes)].slice(0, limit)
}
