import { describe, expect, it } from 'vitest'

import {
  suggestInterviewerQuestions,
  suggestQuestions,
  type SuggestionInput,
} from '@/features/chat/suggestions'

const FEATURES: SuggestionInput['features'] = [
  { group: 'QUALIFICATION', label: 'Java·Spring' },
  { group: 'PREFERENCE', label: '결제 시스템' },
  { group: 'TALENT', label: '주도성' },
]

function input(overrides: Partial<SuggestionInput> = {}): SuggestionInput {
  return {
    type: 'DOCUMENT',
    status: 'ACTIVE',
    counts: { pending: 30, pass: 0, fail: 0, total: 30 },
    hasScores: false,
    features: FEATURES,
    mentions: 0,
    checked: 0,
    interviewed: 0,
    ...overrides,
  }
}

describe('suggestQuestions', () => {
  it('서류 전형은 이 공고의 우대사항, 자격요건, 인재상으로 찾는다', () => {
    expect(suggestQuestions(input())).toEqual([
      "우대사항 '결제 시스템'에 해당하는 지원자 찾아줘",
      '자격요건을 모두 충족한 지원자 찾아줘',
      '인재상이 잘 드러나는 지원자 찾아줘',
    ])
  })

  it('공고 기준이 없으면 그 기준으로 찾는 질문을 내지 않는다', () => {
    expect(suggestQuestions(input({ features: [] }))).toEqual([])
    expect(
      suggestQuestions(input({ features: [{ group: 'QUALIFICATION', label: '학사 이상' }] })),
    ).toEqual(['자격요건을 모두 충족한 지원자 찾아줘'])
  })

  it('키워드를 만들지 못한 긴 열 이름은 질문에 넣지 않는다', () => {
    const long = {
      group: 'PREFERENCE' as const,
      label: '대용량 트래픽 환경에서 결제 서비스를 운영해 본 경험',
    }
    expect(suggestQuestions(input({ features: [long] }))).toEqual([])
  })

  it('결정을 시작했으면 남은 미결정 지원자 가운데서 찾는다', () => {
    const [first] = suggestQuestions(
      input({ counts: { pending: 12, pass: 10, fail: 8, total: 30 } }),
    )
    expect(first).toBe("미결정 12명 중 우대사항 '결제 시스템'에 해당하는 지원자 찾아줘")
  })

  it('모두 결정했으면 확정 전에 결과 리포트를 먼저 권한다', () => {
    const picks = suggestQuestions(input({ counts: { pending: 0, pass: 10, fail: 20, total: 30 } }))
    expect(picks[0]).toBe('이번 전형 결과 리포트 보여줘')
    expect(picks[1]).toBe("우대사항 '결제 시스템'에 해당하는 지원자 찾아줘")
  })

  it('결과를 확정한 전형은 찾기 대신 결과를 돌아본다', () => {
    expect(
      suggestQuestions(
        input({ status: 'CONFIRMED', counts: { pending: 2, pass: 10, fail: 18, total: 30 } }),
      ),
    ).toEqual(['이번 전형 결과 리포트 보여줘', '미결정으로 남은 2명은 어떤 지원자야?'])
  })

  it('지원자가 없으면 추천하지 않는다', () => {
    expect(suggestQuestions(input({ counts: { pending: 0, pass: 0, fail: 0, total: 0 } }))).toEqual(
      [],
    )
  })

  it('평가 전형은 점수가 들어왔는지에 따라 다르게 권한다', () => {
    const base = { type: 'ASSESSMENT' as const, features: [] }
    expect(suggestQuestions(input(base))).toEqual(['평가 결과가 아직 없는 지원자 보여줘'])
    expect(suggestQuestions(input({ ...base, hasScores: true }))).toEqual([
      '평가 점수가 높은 지원자 5명 찾아줘',
      '평가 점수는 높은데 서류 내용과 차이가 큰 지원자 있어?',
    ])
  })

  it('면접 전에는 서류에서 본인 역할을 확인할 지원자를 찾는다', () => {
    expect(suggestQuestions(input({ type: 'INTERVIEW', features: [] }))).toEqual([
      '서류에서 팀 성과와 본인 역할이 구분되지 않는 지원자 찾아줘',
    ])
  })

  it('면접을 마친 지원자가 있으면 답변과 서류의 차이를 먼저 권한다', () => {
    const base = { type: 'INTERVIEW' as const, features: [], interviewed: 2 }
    expect(suggestQuestions(input(base))).toEqual([
      '면접을 마친 지원자 중 답변이 서류 내용과 다른 사람 있어?',
      '서류에서 팀 성과와 본인 역할이 구분되지 않는 지원자 찾아줘',
    ])
    // 범위를 스스로 정한 질문이라 '미결정 N명 중'을 붙이지 않는다
    expect(
      suggestQuestions(input({ ...base, counts: { pending: 3, pass: 2, fail: 1, total: 6 } }))[0],
    ).toBe('면접을 마친 지원자 중 답변이 서류 내용과 다른 사람 있어?')
  })

  it('체크한 지원자가 있으면 그 지원자에 대한 질문을 먼저 권한다', () => {
    expect(suggestQuestions(input({ checked: 1 }))[0]).toBe(
      '체크한 지원자의 강점과 확인할 점을 정리해줘',
    )
    expect(suggestQuestions(input({ checked: 3 }))[0]).toBe('체크한 지원자 3명을 비교해줘')
    expect(suggestQuestions(input({ checked: 3 }))).toHaveLength(3)
  })

  it('멘션은 이번 질문에 붙는 대상이라 체크보다 먼저다', () => {
    expect(suggestQuestions(input({ mentions: 2, checked: 1 }))[0]).toBe(
      '멘션한 지원자 2명을 비교해줘',
    )
  })

  it('한 번에 비교하기 많은 수를 체크했으면 비교를 권하지 않는다', () => {
    expect(suggestQuestions(input({ checked: 6 }))[0]).toBe(
      "우대사항 '결제 시스템'에 해당하는 지원자 찾아줘",
    )
  })

  it('진행 중인 면접 전형에서 한 명을 고르면 면접 질문을 권한다', () => {
    expect(suggestQuestions(input({ type: 'INTERVIEW', features: [], mentions: 1 }))[0]).toBe(
      '멘션한 지원자에게 물어볼 면접 질문 만들어줘',
    )
    expect(
      suggestQuestions(
        input({ type: 'INTERVIEW', status: 'CONFIRMED', features: [], mentions: 1 }),
      )[0],
    ).toBe('멘션한 지원자의 강점과 확인할 점을 정리해줘')
  })
})

describe('suggestInterviewerQuestions', () => {
  const base = { name: '김하늘', answered: false, previousAnswered: false }

  it('면접 전에는 서류에서 확인할 점과 면접 질문을 권한다', () => {
    expect(suggestInterviewerQuestions({ ...base, status: 'SCHEDULED' })).toEqual([
      '김하늘 님의 서류에서 면접 때 확인할 점을 정리해줘',
      '김하늘 님에게 물어볼 면접 질문 만들어줘',
    ])
  })

  it('앞 면접 기록이 있으면 그때 확인하지 못한 점을 권한다', () => {
    expect(
      suggestInterviewerQuestions({ ...base, status: 'SCHEDULED', previousAnswered: true })[1],
    ).toBe('김하늘 님의 이전 면접에서 확인하지 못한 점을 정리해줘')
  })

  it('진행 중에는 답변이 쌓이면 답변에서 더 확인할 점을 먼저 권한다', () => {
    expect(suggestInterviewerQuestions({ ...base, status: 'IN_PROGRESS' })).toEqual([
      '김하늘 님이 프로젝트에서 본인이 한 일을 정리해줘',
      '김하늘 님의 본인 역할을 확인할 질문 하나 더 만들어줘',
    ])
    expect(suggestInterviewerQuestions({ ...base, status: 'IN_PROGRESS', answered: true })[0]).toBe(
      '김하늘 님의 지금까지 답변에서 더 확인할 점을 알려줘',
    )
  })

  it('면접이 끝나면 질문을 더 만들지 않고 답변을 돌아본다', () => {
    expect(suggestInterviewerQuestions({ ...base, status: 'ENDED', answered: true })).toEqual([
      '김하늘 님의 면접 답변을 서류 내용과 비교해줘',
      '김하늘 님의 강점과 더 확인이 필요한 점을 정리해줘',
    ])
  })
})
