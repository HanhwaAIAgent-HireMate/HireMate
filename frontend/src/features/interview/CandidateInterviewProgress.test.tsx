import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { CandidateInterviewProgress } from './CandidateInterviewProgress'

function mockProgress() {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        Response.json([
          {
            applicationId: 'kim',
            status: 'IN_PROGRESS',
            startedAt: null,
            endedAt: null,
            attendees: [
              {
                role: 'HR',
                memberId: 'hr',
                name: '최인사',
                ready: true,
                online: true,
                me: false,
              },
              {
                role: 'PRACTICAL',
                memberId: 'job',
                name: '김실무',
                ready: true,
                online: false,
                me: false,
              },
            ],
          },
          {
            applicationId: 'lee',
            status: 'SCHEDULED',
            startedAt: null,
            endedAt: null,
            attendees: [
              {
                role: 'HR',
                memberId: 'hr',
                name: '최인사',
                ready: false,
                online: false,
                me: false,
              },
              {
                role: 'PRACTICAL',
                memberId: 'job',
                name: '김실무',
                ready: false,
                online: false,
                me: false,
              },
            ],
          },
        ]),
      ),
    ),
  )
}

afterEach(() => vi.unstubAllGlobals())

it('지원자를 바꾸면 그 면접의 상태만 읽어 보여 주고 배정 편집은 제공하지 않는다', async () => {
  mockProgress()
  const client = createQueryClient()
  const view = (applicationId: string) => (
    <QueryClientProvider client={client}>
      <CandidateInterviewProgress stageId="stage" applicationId={applicationId} />
    </QueryClientProvider>
  )
  const { rerender } = render(view('kim'))
  const region = await screen.findByRole('region', { name: '지원자 면접 진행 현황' })
  expect(region).toHaveTextContent('면접 진행 중')
  const people = within(region).getAllByRole('listitem')
  expect(people[0]).toHaveTextContent('인사 최인사준비 완료')
  expect(people[1]).toHaveTextContent('실무 김실무접속 끊김')
  expect(within(region).queryByRole('button')).not.toBeInTheDocument()
  expect(within(region).queryByRole('combobox')).not.toBeInTheDocument()
  rerender(view('lee'))
  expect(region).toHaveTextContent('면접 예정')
  expect(within(region).getAllByText('준비 전')).toHaveLength(2)
  expect(within(region).queryByText('접속 끊김')).not.toBeInTheDocument()
})

it('아직 공통 면접관을 배정하지 않아 진행 현황이 없으면 지원자별 배정 버튼을 만들지 않는다', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json([]))),
  )
  const { container } = render(
    <QueryClientProvider client={createQueryClient()}>
      <CandidateInterviewProgress stageId="stage" applicationId="kim" />
    </QueryClientProvider>,
  )
  await vi.waitFor(() => expect(fetch).toHaveBeenCalled())
  expect(container).toBeEmptyDOMElement()
})
