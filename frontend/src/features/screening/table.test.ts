import { describe, expect, it } from 'vitest'

import type { CandidateAnalysis, CandidateRow, CriterionLine } from '@/features/screening/api'
import {
  criterionCell,
  followUps,
  rowCells,
  talentCell,
  type TableFeature,
  type TalentFit,
} from '@/features/screening/table'

const condition: TableFeature = {
  id: 'Q-01',
  group: 'QUALIFICATION',
  kind: 'CONDITION',
  label: 'Java/Spring 3년',
  text: 'Java/Spring 기반 백엔드 개발 경력 3년 이상',
  important: true,
}
const experience: TableFeature = {
  id: 'P-01',
  group: 'PREFERENCE',
  kind: 'EXPERIENCE',
  label: '장애 대응',
  text: '운영 장애 대응 경험',
  important: false,
}
const talent: TableFeature = {
  id: 'T-1',
  group: 'TALENT',
  kind: 'EXPERIENCE',
  label: '인성',
  text: '인성을 중요시한다',
  important: false,
}

function line(overrides: Partial<CriterionLine>): CriterionLine {
  return {
    criterionId: 'Q-01',
    category: 'QUALIFICATION',
    text: '',
    important: false,
    criterionType: 'CONDITION',
    verdict: 'MET',
    reason: '판정 이유',
    satisfiedParts: [],
    unsatisfiedParts: [],
    unknownParts: [],
    evidence: [],
    recheckCount: 0,
    careerYears: null,
    certificateStatus: null,
    metric: '',
    ...overrides,
  }
}

const row = (analysisStatus: CandidateRow['analysisStatus']) =>
  ({ applicationId: 'a1', name: '정유민', analysisStatus }) as CandidateRow

describe('표 보기 칸', () => {
  it('조건형은 O · X, 경험형은 지표가 있으면 상 · 경험만 있으면 중 · 확인 안 되면 하다', () => {
    expect(criterionCell(condition, line({ verdict: 'MET', careerYears: 5 }))).toMatchObject({
      mark: 'O',
      note: '관련 경력 5년',
    })
    expect(criterionCell(condition, line({ verdict: 'NOT_MET' })).mark).toBe('X')
    expect(
      criterionCell(experience, line({ verdict: 'MET', metric: '장애 복구 시간 30% 단축' })),
    ).toMatchObject({ mark: '상', tone: 'good', note: '장애 복구 시간 30% 단축' })
    expect(
      criterionCell(experience, line({ verdict: 'MET', satisfiedParts: ['원인 분석 · 복구'] })),
    ).toMatchObject({ mark: '중', tone: 'mid', note: '원인 분석 · 복구' })
    expect(criterionCell(experience, line({ verdict: 'PARTIAL' })).mark).toBe('중')
    expect(criterionCell(experience, line({ verdict: 'NOT_MET' })).mark).toBe('하')
    expect(
      criterionCell(experience, line({ verdict: 'UNKNOWN', unknownParts: ['운영 규모'] })),
    ).toMatchObject({ mark: '확인 필요', note: '운영 규모' })
    expect(criterionCell(experience, undefined).mark).toBe('확인 필요')
  })

  it('인재상은 판정 수준을 상 · 중 · 하로 옮기고 한 일을 칸 아래에 쓴다', () => {
    const match = {
      title: '인성을 중요시한다',
      level: 'HIGH' as const,
      evidence: '타 팀 API 명세 조율',
      reason: '직접 조율',
      quote: null,
      metric: '일정 2주 단축',
    }
    expect(talentCell(match)).toMatchObject({
      mark: '상',
      note: '타 팀 API 명세 조율 · 일정 2주 단축',
    })
    expect(talentCell({ ...match, level: 'UNKNOWN', evidence: '' }).mark).toBe('확인 필요')
  })

  it('분석 중이면 칸을 분석 중으로 두고, 열 순서대로 평가 기준과 인재상을 채운다', () => {
    const features = [condition, experience, talent]
    expect(
      rowCells(row('PENDING'), features, undefined, undefined).map((cell) => cell.mark),
    ).toEqual(['분석 중', '분석 중', '분석 중'])

    const analysis = {
      criteria: [line({ criterionId: 'Q-01' }), line({ criterionId: 'P-01', verdict: 'UNKNOWN' })],
    } as CandidateAnalysis
    const talents: TalentFit = {
      items: [
        { title: '인성', level: 'MID', evidence: 'TF 참여', reason: '', quote: null, metric: '' },
      ],
      agent: 'Application Agent',
      stub: false,
    }
    const cells = rowCells(row('DONE'), features, analysis, talents)

    expect(cells.map((cell) => cell.mark)).toEqual(['O', '확인 필요', '중'])
    // 인재상 판정이 아직 오지 않았으면 그 칸만 분석 중이다
    expect(rowCells(row('DONE'), features, analysis, undefined)[2]?.mark).toBe('분석 중')
    expect(followUps(features, cells)).toEqual(['장애 대응'])
  })
})
