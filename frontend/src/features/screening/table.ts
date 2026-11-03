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
 * 칸 표기. 조건형은 O · X, 경험 · 역량형은 상 · 중 · 하다. 경험과 정량 지표가 함께 있으면 상, 경험만 있으면 중,
 * 서류에서 경험이 확인되지 않으면 하이고, 판정하지 못했으면 확인 필요다
 */
export type Mark = 'O' | 'X' | '상' | '중' | '하' | '확인 필요' | '분석 중' | '분석 실패'
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
  '확인 필요': 'unknown',
  '분석 중': 'waiting',
  '분석 실패': 'unknown',
}

// O · 상은 붉은 계열, 중은 노란 계열, X · 하는 파란 계열로 한눈에 갈리게 한다. 붉은 글자는 눈이 덜 피로한 장미색으로 둔다.
// 표 보기와 지원자 카드의 AI 분석이 같은 색을 쓴다
export const TONE_CLASSES: Record<Tone, string> = {
  good: 'bg-rose-100 text-rose-600 dark:bg-rose-950 dark:text-rose-300',
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
 * 지표 없는 충족 · 부분 충족은 중, 서류에서 확인되지 않으면 하다. 판정하지 못했으면 확인 필요다
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
        ? (line.unsatisfiedParts[0] ?? '')
        : line.careerYears != null
          ? `관련 경력 ${line.careerYears}년`
          : line.metric || (line.satisfiedParts[0] ?? '')
  return cell(criterionMark(condition, line), note, line.reason)
}

export const TALENT_MARKS: Record<TalentMatch['level'], Mark> = {
  HIGH: '상',
  MID: '중',
  LOW: '하',
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

/** 추가로 확인할 점 한두 개. 확인 필요 칸의 빠진 부분을 먼저, 없으면 확인 필요인 열 이름을 쓴다 */
export function followUps(features: TableFeature[], cells: Cell[], limit = 2): string[] {
  const unknown = cells
    .map((item, index) => ({ item, feature: features[index] }))
    .filter(({ item }) => item.mark === '확인 필요')
  const notes = unknown.map(({ item, feature }) => item.note || feature.label)
  return [...new Set(notes)].slice(0, limit)
}
