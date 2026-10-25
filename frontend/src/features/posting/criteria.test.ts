import { describe, expect, it } from 'vitest'

import type { ScreeningCriteria } from '@/features/posting/api'
import {
  compactRules,
  draftRule,
  emptyRule,
  hireCountProblem,
  isFilled,
  isStale,
  recommendedDuties,
  ruleProblems,
  rulesFor,
  splitCertificates,
  toCriteriaRequest,
  type RuleForm,
} from '@/features/posting/criteria'

const server: ScreeningCriteria = {
  locked: false,
  hireCount: 2,
  criteriaVersion: 'v1',
  items: [
    {
      saved: true,
      criterion: {
        criterionId: 'Q-01',
        category: 'QUALIFICATION',
        text: 'SQL 작성 경험',
        important: true,
        criterionType: 'COMPOSITE',
        evaluationRules: { met: '설계와 작성 모두', partial: '작성만', unmet: '없음' },
        certificates: ['SQLD', '정보처리기사'],
        ncsUnitCode: '2001020413_19v4',
      },
    },
    {
      saved: false,
      criterion: {
        criterionId: 'P-01',
        category: 'PREFERENCE',
        text: '결제 도메인 경험',
        important: false,
        criterionType: 'SINGLE',
        evaluationRules: { met: '', partial: null, unmet: '' },
        certificates: [],
        ncsUnitCode: null,
      },
    },
  ],
}

const filled: RuleForm = {
  ...emptyRule(),
  criterionType: 'SINGLE',
  met: '있다',
  unmet: '없다',
  basis: '결제 도메인 경험',
}

describe('서류 평가 기준 입력', () => {
  it('공고 문장마다 저장한 기준을 문장으로 짝짓고, 짝이 없는 줄은 빈 기준이다', () => {
    const rules = rulesFor(
      { qualifications: ['새로 쓴 문장', ' SQL 작성 경험 '], preferred: ['결제 도메인 경험'] },
      server,
    )

    expect(rules.qualifications[0]).toEqual(emptyRule())
    expect(rules.qualifications[1]).toEqual({
      important: true,
      criterionType: 'COMPOSITE',
      met: '설계와 작성 모두',
      partial: '작성만',
      unmet: '없음',
      certificates: 'SQLD, 정보처리기사',
      ncsUnitCode: '2001020413_19v4',
      basis: 'SQL 작성 경험',
    })
    // 저장하지 않은 항목(saved: false)은 짝이 있어도 빈 기준이다
    expect(rules.preferred[0]).toEqual(emptyRule())
  })

  it('무엇이든 입력하면 기준이 있는 것이고, 정한 뒤 문장이 바뀌면 확인이 필요하다', () => {
    expect(isFilled(emptyRule())).toBe(false)
    expect(isFilled({ ...emptyRule(), criterionType: 'CONDITION' })).toBe(false)
    expect(isFilled({ ...emptyRule(), important: true })).toBe(true)
    expect(isStale(filled, ' 결제 도메인 경험 ')).toBe(false)
    expect(isStale(filled, '금융 도메인 경험')).toBe(true)
    expect(isStale(emptyRule(), '아무 문장')).toBe(false)
  })

  it('입력한 기준은 충족 · 미충족이, 복합 경험형은 부분 충족도 있어야 한다', () => {
    const certificates = Array.from({ length: 11 }, (_, i) => `자격${i}`).join(',')

    expect(ruleProblems(emptyRule())).toEqual({})
    expect(Object.keys(ruleProblems({ ...emptyRule(), important: true }))).toEqual(['met', 'unmet'])
    expect(Object.keys(ruleProblems({ ...filled, criterionType: 'COMPOSITE' }))).toEqual([
      'partial',
    ])
    expect(ruleProblems({ ...filled, met: 'x'.repeat(501) }).met).toContain('500자')
    expect(ruleProblems({ ...filled, certificates }).certificates).toContain('10개')
  })

  it('선발 인원은 1명부터 1000명까지 정수다', () => {
    expect(hireCountProblem('')).toContain('입력')
    expect(hireCountProblem('0')).not.toBeNull()
    expect(hireCountProblem('2.5')).not.toBeNull()
    expect(hireCountProblem('1001')).toContain('1000')
    expect(hireCountProblem('3')).toBeNull()
  })

  it('문장이 있고 기준을 입력한 줄만, 같은 문장은 한 번만 보낸다', () => {
    const request = toCriteriaRequest(
      3,
      {
        qualifications: [' SQL 작성 경험 ', '', 'Git 협업 경험'],
        preferred: ['결제 도메인 경험', '결제 도메인 경험'],
      },
      {
        qualifications: [
          { ...filled, criterionType: 'COMPOSITE', partial: '작성만', certificates: 'SQLD, ' },
          { ...filled },
          emptyRule(),
        ],
        preferred: [
          { ...filled, partial: '남은 부분 충족' },
          { ...filled, important: true },
        ],
      },
    )

    expect(request.hireCount).toBe(3)
    expect(request.criteria.map((item) => [item.category, item.text])).toEqual([
      ['QUALIFICATION', 'SQL 작성 경험'],
      ['PREFERENCE', '결제 도메인 경험'],
    ])
    expect(request.criteria[0]).toMatchObject({ partial: '작성만', certificates: ['SQLD'] })
    // 부분 충족은 복합 경험형에만 보낸다
    expect(request.criteria[1].partial).toBe('')
  })

  it('공고를 저장하면 빠지는 빈 줄의 기준도 뺀다', () => {
    const rules = {
      qualifications: [filled, emptyRule(), { ...filled, important: true }],
      preferred: [],
    }

    const next = compactRules({ qualifications: ['가', '  ', '나'], preferred: [] }, rules)

    expect(next.qualifications).toEqual([filled, { ...filled, important: true }])
  })

  it('AI 초안은 중요 표시를 그대로 두고 유형 · 판정 기준 · 자격증만 채운다', () => {
    const next = draftRule(
      { ...emptyRule(), important: true },
      {
        criterionType: 'CONDITION',
        met: '보유',
        partial: null,
        unmet: '없음',
        certificates: ['SQLD'],
      },
      ' SQLD 보유 ',
    )

    expect(next).toEqual({
      ...emptyRule(),
      important: true,
      criterionType: 'CONDITION',
      met: '보유',
      unmet: '없음',
      certificates: 'SQLD',
      basis: 'SQLD 보유',
    })
  })

  it('중요 추천을 목록 안 순서 → 근거 주요 업무로 바꾼다', () => {
    const advice = {
      qualifications: [{ index: 1, duty: '결제 API 개발' }],
      preferred: [{ index: 0, duty: '정산' }],
    }

    expect([...recommendedDuties(advice, 'qualifications')]).toEqual([[1, '결제 API 개발']])
    expect([...recommendedDuties(advice, 'preferred')]).toEqual([[0, '정산']])
  })

  it('자격증은 쉼표나 줄바꿈으로 나눈다', () => {
    expect(splitCertificates(' 정보처리기사,SQLD\n\n리눅스마스터 ,')).toEqual([
      '정보처리기사',
      'SQLD',
      '리눅스마스터',
    ])
  })
})
