import { describe, expect, it } from 'vitest'

import type { CandidateDetail } from '@/features/screening/api'
import { groupByDocument, underlineSpans } from '@/features/screening/evidence'

// 직무와 무관하게 쓰이는지 매장 운영 서류로 확인한다
const documents = [
  {
    type: 'RESUME',
    fileName: 'r.pdf',
    text: '가 마트 점장 2020.01 ~ 2022.12\n재고 대장을 바코드로\n바꿨습니다.',
  },
  { type: 'PORTFOLIO', fileName: 'p.pdf', text: '매일 40분 걸리던 재고 맞추기가 12분이 됐습니다.' },
] as unknown as CandidateDetail['documents']

describe('근거 모달의 서류별 근거 묶기', () => {
  it('PDF 줄바꿈이 달라도 원문에서 찾고, 문서 종류를 모르면 원문이 있는 서류로 묶는다', () => {
    const groups = groupByDocument(
      [
        { document: 'RESUME', sentence: '재고 대장을 바코드로 바꿨습니다.' },
        { document: null, sentence: '매일 40분 걸리던 재고 맞추기가 12분이 됐습니다.' },
        { document: 'RESUME', sentence: '서류에 없는 문장입니다.' },
      ],
      documents,
    )

    expect(groups.map((group) => [group.type, group.sentences.length])).toEqual([
      ['RESUME', 1],
      ['PORTFOLIO', 1],
    ])
  })
})

describe('근거 밑줄 구간', () => {
  it('이어 붙은 근거 문장은 밑줄 하나로 세고, 떨어진 문장은 따로 센다', () => {
    const text =
      '재고 대장을 만들었습니다. 바코드로 바꿨습니다.\n다른 이야기입니다.\n12분이 됐습니다.'
    const spans = underlineSpans(text, [
      '재고 대장을 만들었습니다.',
      '바코드로 바꿨습니다.',
      '12분이 됐습니다.',
    ])

    expect(spans.map((span) => text.slice(span.index, span.index + span.length))).toEqual([
      '재고 대장을 만들었습니다. 바코드로 바꿨습니다.',
      '12분이 됐습니다.',
    ])
  })
})
