import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewRoomPage } from '@/pages/interviewer/InterviewRoomPage'

const question = (questionId: string, text: string, interviewerRole: string, answer = '') => ({
  questionId,
  text,
  source: 'AI',
  answer,
  reason: null,
  interviewerRole,
  parentQuestionId: null,
  version: 0,
})
const workspace = (status: string) => ({
  session: {
    stageId: 's1',
    applicationId: 'a1',
    hrMemberId: 'hr1',
    practicalMemberId: 'kim',
    status,
    startedAt: null,
    endedAt: null,
    version: 1,
  },
  myRole: 'PRACTICAL',
  personalMemo: '',
  previous: [],
  schedule: null,
  questions: [
    {
      question: question('q1', '원장 재설계에서 직접 정한 부분은?', 'PRACTICAL'),
      canAnswer: status === 'IN_PROGRESS',
      canRequestFollowUp: false,
      canDelete: false,
      readOnlyReason: status === 'IN_PROGRESS' ? null : '면접 시작 전',
    },
    {
      question: question('q2', '의견이 갈렸던 경험은?', 'HR', '일정을 두고 조율했다'),
      canAnswer: false,
      canRequestFollowUp: false,
      canDelete: false,
      readOnlyReason: '다른 면접관 담당',
    },
  ],
})

function mockServer() {
  // 칸 너비 조절(react-resizable-panels)이 쓰는 브라우저 API. jsdom에는 없다
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  const posts: string[] = []
  let status = 'SCHEDULED'
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      if (typeof input === 'string')
        return Promise.resolve(
          Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' }),
        )
      const url = new URL(input.url).pathname
      if (input.method === 'POST') {
        posts.push(url)
        status = 'IN_PROGRESS'
        return Promise.resolve(Response.json(workspace(status)))
      }
      const routes: Record<string, unknown> = {
        '/api/interviewer/sessions': {
          items: [
            {
              stageId: 's1',
              applicationId: 'a1',
              recruitmentId: 'r1',
              recruitmentTitle: '결제 플랫폼 백엔드 개발자',
              stageName: '1차 기술 면접',
              applicantName: '김하늘',
              schedule: null,
              myRole: 'PRACTICAL',
              status,
            },
          ],
          total: 1,
          page: 0,
          size: 50,
        },
        '/api/interviewer/sessions/s1/a1': workspace(status),
      }
      return Promise.resolve(
        url in routes
          ? Response.json(routes[url])
          : Response.json({ code: 'NOT_FOUND' }, { status: 404 }),
      )
    }),
  )
  return posts
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InterviewRoomPage', () => {
  it('[면접 시작]을 누르면 내 담당 질문에 기록할 수 있고, 다른 면접관 질문은 기록만 보인다', async () => {
    const posts = mockServer()
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider
          router={createMemoryRouter(
            [{ path: '/interviewer/stages/:stageId', element: <InterviewRoomPage /> }],
            { initialEntries: ['/interviewer/stages/s1'] },
          )}
        />
      </QueryClientProvider>,
    )

    expect(await screen.findByText('일정 미정 · 1명')).toBeInTheDocument()
    expect(await screen.findByLabelText('원장 재설계에서 직접 정한 부분은? 답변')).toBeDisabled()
    expect(screen.getByText('면접 시작 전이라 기록할 수 없어요.')).toBeInTheDocument()
    expect(screen.getByText('일정을 두고 조율했다')).toBeInTheDocument()
    expect(screen.getByText('인사 담당')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '면접 시작' }))
    await vi.waitFor(() => expect(posts).toContain('/api/interviewer/sessions/s1/a1/start'))
    expect(await screen.findByRole('button', { name: '면접 종료' })).toBeInTheDocument()
    expect(screen.getByLabelText('원장 재설계에서 직접 정한 부분은? 답변')).toBeEnabled()
  })
})
