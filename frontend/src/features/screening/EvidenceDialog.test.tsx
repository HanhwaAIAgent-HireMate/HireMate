import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CandidateDetail } from '@/features/screening/api'
import { EvidenceDialog } from '@/features/screening/EvidenceDialog'

// 직무와 무관하게 쓰이는지 매장 운영 서류로 확인한다
const documents = [
  {
    type: 'PORTFOLIO',
    fileName: 'p.pdf',
    text: '매장 리뉴얼 프로젝트\n발주 전에 재고를 맞추는 데 매일 40분이 걸렸습니다.\n재고 대장을 바코드로 바꿨습니다.\n바꾼 뒤에는 12분이면 끝났습니다.',
  },
] as unknown as CandidateDetail['documents']

describe('판정 근거 모달', () => {
  it('근거가 나온 서류 전체를 보여 주고 근거 문장에만 밑줄을 친다', () => {
    render(
      <EvidenceDialog
        open
        onOpenChange={() => {}}
        title="재고 관리 개선"
        reason="재고 대장을 바꾼 본인 행동과 결과가 확인된다."
        metric="12분"
        quotes={[{ document: 'PORTFOLIO', sentence: '재고 대장을 바코드로 바꿨습니다.' }]}
        documents={documents}
      />,
    )

    // 프로젝트 제목 같은 앞뒤 문맥도 함께 보인다
    expect(screen.getByText(/매장 리뉴얼 프로젝트/)).toBeInTheDocument()
    const marks = document.querySelectorAll('mark')
    expect([...marks].map((mark) => mark.textContent)).toEqual(['재고 대장을 바코드로 바꿨습니다.'])
  })

  it('원문에서 찾지 못한 근거만 있으면 알린다', () => {
    render(
      <EvidenceDialog
        open
        onOpenChange={() => {}}
        title="재고 관리 개선"
        reason=""
        metric=""
        quotes={[{ document: 'PORTFOLIO', sentence: '서류에 없는 문장입니다.' }]}
        documents={documents}
      />,
    )

    expect(screen.getByText('서류에서 근거 문장을 찾지 못했어요.')).toBeInTheDocument()
  })
})
