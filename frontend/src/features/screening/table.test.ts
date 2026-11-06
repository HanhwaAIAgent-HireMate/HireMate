import { describe, expect, it } from 'vitest'

import type { CandidateAnalysis, CandidateRow, CriterionLine } from '@/features/screening/api'
import {
  checkPoints,
  settingPoints,
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
    noRecord: false,
    brief: '',
    settingNote: '',
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
    // 서류에 관련 기록이 아예 없어도 하이고, 칸 아래에 그 사실을 쓴다. 조건형은 그대로 X다
    expect(criterionCell(experience, line({ verdict: 'NOT_MET', noRecord: true }))).toMatchObject({
      mark: '하',
      note: '서류에 해당 내용 없음',
    })
    expect(criterionCell(condition, line({ verdict: 'NOT_MET', noRecord: true })).mark).toBe('X')
    expect(
      criterionCell(experience, line({ verdict: 'UNKNOWN', unknownParts: ['운영 규모'] })),
    ).toMatchObject({ mark: '확인 필요', note: '운영 규모' })
    expect(criterionCell(experience, undefined).mark).toBe('확인 필요')
  })

  it('인재상은 판정 수준을 행동 확인 · 일부 확인 · 미확인으로 옮기고 한 일을 칸 아래에 쓴다', () => {
    const match = {
      title: '인성을 중요시한다',
      level: 'HIGH' as const,
      evidence: '타 팀 API 명세 조율',
      reason: '직접 조율',
      quote: null,
      metric: '일정 2주 단축',
    }
    expect(talentCell(match)).toMatchObject({
      mark: '행동 확인',
      note: '타 팀 API 명세 조율 · 일정 2주 단축',
    })
    expect(talentCell({ ...match, level: 'MID' }).mark).toBe('일부 확인')
    expect(talentCell({ ...match, level: 'LOW' }).mark).toBe('미확인')
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

    expect(cells.map((cell) => cell.mark)).toEqual(['O', '확인 필요', '일부 확인'])
    // 인재상 판정이 아직 오지 않았으면 그 칸만 분석 중이다
    expect(rowCells(row('DONE'), features, analysis, undefined)[2]?.mark).toBe('분석 중')
    expect(followUps(features, cells)).toEqual(['장애 대응'])
  })

  it('확인할 점은 번호 · 공고 문장 없이 항목 이름과 판정 요약(없으면 빠진 부분)만 쓰고, 평가 기준 없음 알림은 묶는다', () => {
    const analysis = {
      criteria: [
        line({ criterionId: 'Q-01', criterionType: 'COMPOSITE' }),
        line({
          criterionId: 'Q-02',
          text: 'SQL을 작성하고 DB 성능을 개선한 경험',
          criterionType: 'COMPOSITE',
          verdict: 'NOT_MET',
          unsatisfiedParts: ['SQL 작성', 'DB 성능 개선'],
          brief: 'SQL 작성에 참여하지 않았다고 기재',
        }),
        line({
          criterionId: 'P-01',
          text: '운영 장애 대응 경험',
          category: 'PREFERENCE',
          criterionType: 'COMPOSITE',
          verdict: 'UNKNOWN',
          reason: '장애였는지 자료만으로 판단할 수 없다.',
          unknownParts: ['장애 원인 분석', '복구 검증'],
        }),
        line({ criterionId: 'P-02', category: 'PREFERENCE', verdict: 'NOT_MET' }),
      ],
      holds: [{ text: "P-01 '운영 장애 대응 경험' 확인 필요: 장애였는지 …", source: '공고' }],
      checks: [
        {
          text: "'Git 협업'에 맞는 평가 기준이 없어 AI가 만든 판정 기준 초안으로 판정했어요.",
          source: '공고',
        },
        {
          text: "'JUnit 테스트'에 맞는 평가 기준이 없어 AI가 만든 판정 기준 초안으로 판정했어요. 담당자 확인: 'JUnit'만 인정할지, 다른 테스트 도구도 인정할지 확인이 필요해요.",
          source: '공고',
        },
        { text: "Q-02 'SQL을 작성하고 DB 성능을 개선한 경험': 확인되지 않는다.", source: '공고' },
      ],
    } as unknown as CandidateAnalysis

    expect(checkPoints(analysis, new Map([['운영 장애 대응 경험', '장애 대응']]))).toEqual([
      {
        key: 'P-01',
        label: '장애 대응',
        mark: '확인 필요',
        summary: '장애 원인 분석 · 복구 검증',
        detail: '장애였는지 자료만으로 판단할 수 없다.',
      },
      {
        key: 'Q-02',
        label: 'SQL을 작성하고 DB 성능을 개선한 경험',
        mark: '하',
        summary: 'SQL 작성에 참여하지 않았다고 기재',
        detail: '판정 이유',
      },
    ])
    // 평가 기준이 없다는 알림은 지원자에게 물을 점이 아니라 평가 설정 검토다
    // AI 초안이 고른 해석은 담당자가 확정하도록 따로 보인다
    expect(settingPoints(analysis, new Map())).toEqual([
      {
        key: 'confirm-JUnit 테스트',
        label: 'JUnit 테스트',
        mark: null,
        summary: "'JUnit'만 인정할지, 다른 테스트 도구도 인정할지 확인이 필요해요.",
        detail:
          'AI 판정 기준 초안이 고른 해석이에요. 평가 기준을 정해 저장하면 그 기준으로 다시 판정해요.',
      },
      {
        key: 'no-rubric',
        label: '평가 기준 없음',
        mark: null,
        summary: '공고 항목 2개는 AI가 만든 판정 기준 초안으로 판정',
        detail: 'Git 협업\nJUnit 테스트',
      },
    ])
  })

  it('기준이 정하지 않아 갈린 판정은 지원자 확인할 점이 아니라 설정 검토로 보인다', () => {
    // 직무와 무관하게 쓰이는지 마케팅 공고 예시로 확인한다
    const undecided = line({
      criterionId: 'P-01',
      text: '대규모 캠페인 운영 경험',
      category: 'PREFERENCE',
      verdict: 'UNKNOWN',
      reason: '월 예산 3억 원 캠페인을 직접 운영했으나 대규모 기준이 정해져 있지 않다.',
      brief: '월 예산 3억 원 캠페인 직접 운영',
      settingNote: "기준에 '대규모'의 예산 · 규모 기준이 정해져 있지 않음",
    })
    const analysis = {
      criteria: [undecided],
      holds: [],
      checks: [],
    } as unknown as CandidateAnalysis

    expect(checkPoints(analysis, new Map())).toEqual([])
    expect(settingPoints(analysis, new Map())).toEqual([
      {
        key: 'setting-P-01',
        label: '대규모 캠페인 운영 경험',
        mark: null,
        summary: "기준에 '대규모'의 예산 · 규모 기준이 정해져 있지 않음",
        detail:
          '월 예산 3억 원 캠페인 직접 운영\n월 예산 3억 원 캠페인을 직접 운영했으나 대규모 기준이 정해져 있지 않다.',
      },
    ])
    // 지원자에게도 확인할 부분이 남아 있으면 확인할 점에도 남는다
    const both = { ...analysis, criteria: [{ ...undecided, unknownParts: ['본인 담당 범위'] }] }
    expect(checkPoints(both, new Map()).map((item) => item.key)).toEqual(['P-01'])
  })

  it('서류 주의 신호는 확인할 점 맨 앞에 주의 카드로 보인다', () => {
    const analysis = {
      criteria: [
        line({
          criterionId: 'P-01',
          category: 'PREFERENCE',
          verdict: 'UNKNOWN',
          unknownParts: ['범위'],
        }),
      ],
      holds: [],
      checks: [
        {
          text: '1년 미만 재직 3회 (가 9개월, 나 10개월, 다 8개월)',
          source: '이력서',
          title: '잦은 이직',
          warning: true,
        },
        { text: '서류를 읽지 못했어요', source: '제출 문서' },
      ],
    } as unknown as CandidateAnalysis

    const points = checkPoints(analysis, new Map())

    expect(points.map((item) => [item.label, item.warning ?? false])).toEqual([
      ['잦은 이직', true],
      ['', false],
      ['알림', false],
    ])
  })
})
