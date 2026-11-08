import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CandidateAnalysis } from '@/features/screening/api'
import { DigestView } from '@/features/screening/DigestView'

const evidence = [{ document: 'RESUME' as const, sentence: '결제 승인 API를 개발했습니다.' }]
const digest: CandidateAnalysis['digests'][number] = {
  document: 'RESUME',
  sections: [
    {
      title: '경력',
      layout: 'table',
      columns: ['기간', '소속 · 역할', '주요 업무'],
      rows: [
        { title: '', cells: ['2022.03 ~ 2025.02', '가상커머스 · 백엔드', ''], tags: [], evidence },
      ],
      tags: [],
      items: [],
    },
    {
      title: '프로젝트',
      layout: 'cards',
      columns: ['문제', '해결', '성과'],
      rows: [
        {
          title: '좌석 예매 동시성',
          cells: ['중복 예매', 'Redis 락', '37건 → 0건'],
          tags: ['Redis', 'Kafka'],
          evidence: [],
        },
      ],
      tags: ['Java'],
      items: ['정보처리기사 (2021.06)'],
    },
  ],
}

describe('이력서 · 포트폴리오 정리 보기', () => {
  it('표 · 카드 · 기술 칩 · 자격 줄을 보여 주고, 빈 칸은 -로 둔다', () => {
    render(<DigestView digest={digest} />)

    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('가상커머스 · 백엔드')).toBeInTheDocument()
    expect(screen.getByText('01')).toBeInTheDocument()
    expect(screen.getByText('Java')).toBeInTheDocument()
    expect(screen.getByText('정보처리기사 (2021.06)')).toBeInTheDocument()
    expect(screen.getAllByText('-')).toHaveLength(1)
  })

  it('포트폴리오 카드는 문제 · 해결 · 기술 · 성과 순서로 보이고 원문 링크는 없다', () => {
    render(<DigestView digest={digest} />)

    const card = screen.getByText('좌석 예매 동시성').closest('li') as HTMLElement
    const labels = within(card)
      .getAllByRole('term')
      .map((term) => term.textContent)
    expect(labels).toEqual(['문제', '해결', '기술', '성과'])
    expect(within(card).getByText('Kafka')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.queryByText('원문')).not.toBeInTheDocument()
  })
})
