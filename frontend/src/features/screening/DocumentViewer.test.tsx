import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CandidateDetail } from '@/features/screening/api'
import { DocumentViewer } from '@/features/screening/DocumentViewer'

vi.mock('@/features/screening/api', () => ({
  useCandidateAnalysis: () => ({
    isPending: false,
    data: {
      agent: 'Application Agent',
      stub: false,
      criteria: [],
      conditions: [],
      notable: [],
      checks: [],
      holds: [],
      highlights: [],
      summaries: [],
      digests: [
        {
          document: 'RESUME',
          sections: [
            {
              title: '경력',
              layout: 'table',
              columns: ['업무'],
              rows: [{ title: '', cells: ['이력서 요약'], tags: [], evidence: [] }],
              tags: [],
              items: [],
            },
          ],
        },
        {
          document: 'PORTFOLIO',
          sections: [
            {
              title: '프로젝트',
              layout: 'table',
              columns: ['이름'],
              rows: [{ title: '', cells: ['포트폴리오 요약'], tags: [], evidence: [] }],
              tags: [],
              items: [],
            },
          ],
        },
      ],
    },
  }),
}))

vi.mock('@/features/screening/table', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/screening/table')>()),
  useTalentFit: () => ({ data: { items: [] }, isPending: false }),
  useCandidateTable: () => ({ data: { features: [] } }),
}))

const detail = {
  row: { applicationId: 'app-1', analysisStatus: 'DONE' },
  documents: [
    { type: 'RESUME', fileName: 'resume.pdf', text: '이력서 원문입니다.' },
    { type: 'PORTFOLIO', fileName: 'portfolio.pdf', text: '포트폴리오 원문입니다.' },
  ],
  normalized: [],
  originalsWithName: ['RESUME'],
} as unknown as CandidateDetail

describe('서류 원문 보기', () => {
  it.each([
    ['이력서', '이력서 요약', '이력서 원문입니다.'],
    ['포트폴리오', '포트폴리오 요약', '포트폴리오 원문입니다.'],
  ])('%s에서 요약과 원문을 전환한다', (tab, summary, original) => {
    render(<DocumentViewer stageId="stage-1" recruitmentId="recruit-1" detail={detail} />)
    fireEvent.click(screen.getByRole('tab', { name: tab }))
    expect(screen.getByText(summary)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '원문 보기' }))
    expect(screen.getByText(original)).toBeInTheDocument()
    expect(screen.queryByText(summary)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '정리 보기' }))
    expect(screen.getByText(summary)).toBeInTheDocument()
  })
})
