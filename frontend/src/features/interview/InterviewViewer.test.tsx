import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { InterviewViewer } from './InterviewViewer'
import type { CandidateDetail } from '@/features/screening/api'

vi.mock('@/features/interview/api', () => ({
  useInterview: () => ({ data: { questions: [], previous: [], schedule: null } }),
  useInterviewPreparing: () => ({ isPending: true, data: undefined }),
  useInterviewActions: () => ({ regenerate: { isPending: false } }),
}))

describe('면접 질문 로딩', () => {
  it('첫 지원자의 생성 상태를 확인하는 동안 로딩을 표시한다', () => {
    render(
      <InterviewViewer
        stageId="stage"
        recruitmentId="recruit"
        detail={{ row: { applicationId: 'kim' } } as CandidateDetail}
        editable
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent('질문 생성 중이에요')
    expect(screen.queryByText(/아직 질문이 없어요/)).not.toBeInTheDocument()
  })
})
