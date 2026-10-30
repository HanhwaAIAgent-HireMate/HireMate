import { act, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ReportBody } from './ReportBody'
import type { ReportView } from './types'

// jsdom에는 SVG 레이아웃이 없어 차트는 이름만 그린다
vi.mock('./EChart', () => ({
  EChart: ({ label }: { label: string }) => <div role="img" aria-label={label} />,
}))

const report: ReportView = {
  bundle: {
    kind: 'COMPARE',
    stageId: 's',
    title: '백엔드 개발자',
    asOf: '2026-10-27T14:20:00Z',
    focus: '협업',
    brief: true,
    stages: [],
    applicants: [
      { number: 'A-0017', careerYears: 5, lastCompany: null },
      { number: 'A-0025', careerYears: 3, lastCompany: null },
    ],
    targets: ['A-0017', 'A-0025'],
    totalKey: null,
    areas: [],
    metrics: [],
    facts: [
      { id: '1', applicant: 'A-0017', stageId: 's', key: 'q', label: 'Q-04 협업', value: 'MET' },
      {
        id: '2',
        applicant: 'A-0025',
        stageId: 's',
        key: 'q',
        label: 'Q-04 협업',
        value: 'NOT_MET',
      },
    ],
    evidence: [
      {
        id: 'e1',
        applicant: 'A-0017',
        stageId: 's',
        agent: 'application',
        text: '리뷰 규칙을 직접 만든 경험이 확인돼요.',
        source: '자기소개서 3번',
        quote: '팀 PR 리뷰 규칙을 만들었다',
        label: '협업',
        verdict: 'MET',
      },
    ],
  },
  spec: {
    title: '협업 관점 비교',
    summary: 'A-0017은 협업 항목을 충족했어요.',
    skills: [],
    sections: [
      {
        title: '한눈에 보기',
        takeaway: 'A-0025는 협업 근거가 확인되지 않았어요.',
        blocks: [
          {
            type: 'rings',
            title: '관점 도넛',
            caption: '협업 충족 비율이에요.',
            views: [{ label: '협업', keys: ['q'] }],
            applicants: ['A-0017', 'A-0025'],
          },
          {
            type: 'matrix',
            title: '판정',
            keys: ['q'],
            applicants: ['A-0017', 'A-0025'],
          },
          {
            type: 'evidence',
            title: '협업 근거',
            items: [
              {
                applicant: 'A-0025',
                keywords: ['협업 경험'],
                text: '협업 경험은 확인되지 않았어요.',
                evidence: [],
              },
              { applicant: 'A-0017', keywords: ['PR 리뷰 규칙'], text: '', evidence: ['e1'] },
            ],
          },
        ],
      },
    ],
  },
  names: { 'A-0017': '정지호', 'A-0025': '김지우' },
  skills: ['compare'],
  specialists: [],
  fallback: false,
}

describe('리포트 본문', () => {
  it('섹션 읽을 점과 차트, 이름을 붙인 판정 칸을 그린다', () => {
    render(<ReportBody report={report} />)
    const section = screen.getByRole('region', { name: '한눈에 보기' })
    expect(section).toHaveTextContent('김지우(A-0025)는 협업 근거가 확인되지 않았어요.')
    expect(screen.getByText('정지호(A-0017)은 협업 항목을 충족했어요.')).toBeInTheDocument()
    expect(within(section).getByText('관점 도넛')).toBeInTheDocument()
    expect(section).toHaveTextContent('평가 관점')
    expect(section).toHaveTextContent('배경 강조 = 차이 있는 관점')
    expect(section).toHaveTextContent('✓ 충족')
    expect(section).toHaveTextContent('✕ 미충족')
    expect(section).toHaveTextContent('정지호')
  })

  it('근거는 지원자마다 한 카드에 키워드, AI 분석, 원문 순서로 보여 준다', () => {
    render(<ReportBody report={report} />)
    const text = screen.getByRole('region', { name: '한눈에 보기' }).textContent ?? ''
    const cards = text.slice(text.indexOf('협업 근거'))
    expect(cards.indexOf('정지호')).toBeLessThan(cards.indexOf('김지우'))
    const order = ['키워드', 'PR 리뷰 규칙', 'AI 분석', '리뷰 규칙을 직접 만든', '원문', '“팀 PR']
    const at = order.map((word) => cards.indexOf(word))
    expect(at.every((index) => index >= 0)).toBe(true)
    expect(at).toEqual([...at].sort((a, b) => a - b))
    expect(cards).toContain('서류 Agent')
    expect(cards).toContain('근거 문장 없음 · 다음 전형에서 확인')
  })

  it('예전 리포트의 한 줄 근거는 AI 분석과 원문으로 나눠 보여 준다', () => {
    const legacy: ReportView = {
      ...report,
      bundle: {
        ...report.bundle,
        evidence: [
          {
            id: 'e1',
            applicant: 'A-0017',
            stageId: 's',
            agent: 'application',
            text: '리뷰를 이끌었다. (원문: 팀 PR 리뷰 규칙을 만들었다)',
            source: '이력서',
          },
        ],
      },
    }
    render(<ReportBody report={legacy} />)
    expect(screen.getByText('“팀 PR 리뷰 규칙을 만들었다”')).toBeInTheDocument()
    expect(screen.queryByText(/원문:/)).not.toBeInTheDocument()
  })

  it('인쇄(PDF)할 때는 이름 없이 지원자번호만 보여 준다', () => {
    render(<ReportBody report={report} />)
    act(() => {
      window.dispatchEvent(new Event('beforeprint'))
    })
    const body = document.body.textContent ?? ''
    expect(body).not.toContain('정지호')
    expect(body).not.toContain('김지우')
    expect(body).toContain('A-0025는 협업 근거가 확인되지 않았어요.')
    act(() => {
      window.dispatchEvent(new Event('afterprint'))
    })
    expect(document.body.textContent).toContain('정지호')
  })
})

describe('영역 점수 표', () => {
  it('점수가 빈(보류) 지원자는 0점이 아니라 확인 필요로 보여 준다', () => {
    const scored: ReportView = {
      ...report,
      bundle: {
        ...report.bundle,
        facts: [
          ...report.bundle.facts,
          {
            id: 's1',
            applicant: 'A-0017',
            stageId: 's',
            key: 'pref',
            label: '우대',
            value: 40,
            max: 50,
          },
        ],
      },
      spec: {
        ...report.spec,
        sections: [
          {
            title: '점수',
            takeaway: '우대사항 점수가 빈 지원자가 있어요.',
            blocks: [
              {
                type: 'rings',
                title: '영역 점수',
                caption: '',
                views: [
                  { label: '우대사항', keys: ['pref'] },
                  { label: '협업', keys: ['q'] },
                ],
                applicants: ['A-0017', 'A-0025'],
              },
            ],
          },
        ],
      },
    }
    render(<ReportBody report={scored} />)
    const section = screen.getByRole('region', { name: '점수' })
    expect(section).toHaveTextContent('평가 관점')
    expect(section).toHaveTextContent('확인 필요')
  })
})
