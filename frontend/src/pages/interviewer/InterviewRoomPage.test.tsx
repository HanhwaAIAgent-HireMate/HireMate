import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { StrictMode } from 'react'
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
  personalMemoVersion: 0,
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

function mockServer(
  options: {
    status?: string
    /** 내가 이미 준비 완료했나 */
    ready?: boolean
    /** 상대 면접관(인사)이 준비 완료했나. 기본은 준비 완료 */
    otherReady?: boolean
    otherOnline?: boolean
    unassigned?: boolean
    holdAnswer?: boolean
    failAnswer?: boolean
    stageActive?: boolean
    /** 내 면접 목록에서 a1보다 먼저 오는 지원자 */
    listedBefore?: Record<string, unknown>[]
    scheduledAt?: string
  } = {},
) {
  // 칸 너비 조절(react-resizable-panels)이 쓰는 브라우저 API. jsdom에는 없다
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  )
  // Chat이 새 말풍선으로 내리는 브라우저 API. jsdom에는 없다
  Element.prototype.scrollIntoView = vi.fn()
  const posts: string[] = []
  let status = options.status ?? 'SCHEDULED'
  let ready = options.ready ?? false
  const requests: string[] = []
  let releaseAnswer = () => {}
  const answerGate = new Promise<void>((resolve) => {
    releaseAnswer = resolve
  })
  const savedAnswers: string[] = []
  let savedAnswer = ''
  const makeWorkspace = () => {
    const value = workspace(status)
    value.questions[0].question.answer = savedAnswer
    if (options.unassigned) value.questions[0].question.interviewerRole = ''
    return value
  }
  const attendance = () => ({
    stageActive: options.stageActive ?? true,
    attendees: [
      {
        role: 'HR',
        memberId: 'hr1',
        name: '최인사',
        ready: options.otherReady ?? true,
        online: options.otherOnline ?? true,
        me: false,
      },
      { role: 'PRACTICAL', memberId: 'kim', name: '김실무', ready, online: true, me: true },
    ],
  })
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      if (typeof input === 'string')
        return Promise.resolve(
          Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' }),
        )
      const url = new URL(input.url).pathname
      requests.push(`${input.method} ${url}`)
      if (url.endsWith('/events')) {
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode('event: connected\ndata: {}\n\n'))
            },
          }),
          { headers: { 'Content-Type': 'text/event-stream' } },
        )
      }
      if (url.endsWith('/ready')) {
        posts.push(`${input.method} ${url}`)
        ready = input.method === 'POST'
        // 서버처럼 두 면접관이 모두 준비 완료하고 접속 중이면 그 자리에서 시작한다
        if (ready && (options.otherReady ?? true) && (options.otherOnline ?? true))
          status = 'IN_PROGRESS'
        return Response.json(attendance())
      }
      if (input.method === 'POST') {
        posts.push(url)
        status = url.endsWith('/end') ? 'ENDED' : 'IN_PROGRESS'
        return Response.json(makeWorkspace())
      }
      if (input.method === 'PUT' && url.endsWith('/answer')) {
        const body = (await input.json()) as { answer: string }
        if (options.holdAnswer) await answerGate
        if (options.failAnswer) return Response.json({ code: 'SAVE_FAILED' }, { status: 500 })
        savedAnswer = body.answer
        savedAnswers.push(body.answer)
        return Response.json({
          questions: makeWorkspace().questions.map((item) => ({ ...item.question, version: 1 })),
        })
      }
      const routes: Record<string, unknown> = {
        '/api/interviewer/sessions': {
          items: [
            ...(options.listedBefore ?? []),
            {
              stageId: 's1',
              applicationId: 'a1',
              recruitmentId: 'r1',
              recruitmentTitle: '결제 플랫폼 백엔드 개발자',
              stageName: '1차 기술 면접',
              applicantName: '김하늘',
              schedule: options.scheduledAt
                ? { scheduledAt: options.scheduledAt, interviewers: '' }
                : null,
              myRole: 'PRACTICAL',
              status,
            },
          ],
          total: 1 + (options.listedBefore?.length ?? 0),
          page: 0,
          size: 50,
        },
        '/api/interviewer/sessions/s1/a1': makeWorkspace(),
        '/api/interviewer/sessions/s1/a1/attendance': attendance(),
        '/api/interviewer/sessions/s1/a1/opinions': [
          {
            memberId: 'kim',
            role: 'PRACTICAL',
            name: '김실무',
            mine: true,
            submitted: false,
            recommendation: null,
            comment: null,
            updatedAt: null,
            edited: false,
            unassigned: false,
          },
        ],
        '/api/stages/s1/tabs': [{ id: 't1', name: '새 탭', selectedCount: 0, canRestore: false }],
        '/api/stages/s1/tabs/t1/chat': [],
      }
      return Promise.resolve(
        url in routes
          ? Response.json(routes[url])
          : Response.json({ code: 'NOT_FOUND' }, { status: 404 }),
      )
    }),
  )
  return { posts, requests, releaseAnswer, savedAnswers }
}

afterEach(() => {
  vi.unstubAllGlobals()
})

function renderRoom() {
  return render(
    <StrictMode>
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider
          router={createMemoryRouter(
            [{ path: '/interviewer/stages/:stageId', element: <InterviewRoomPage /> }],
            { initialEntries: ['/interviewer/stages/s1'] },
          )}
        />
      </QueryClientProvider>
    </StrictMode>,
  )
}

describe('InterviewRoomPage', () => {
  it('지원자를 고르지 않고 전형으로 들어오면 왼쪽 목록 맨 위 지원자를 연다', async () => {
    const { requests } = mockServer({
      scheduledAt: '2026-11-03T02:00:00Z',
      listedBefore: [
        {
          stageId: 's1',
          applicationId: 'a0',
          recruitmentId: 'r1',
          recruitmentTitle: '결제 플랫폼 백엔드 개발자',
          stageName: '1차 기술 면접',
          applicantName: '박서준',
          schedule: null,
          myRole: 'PRACTICAL',
          status: 'SCHEDULED',
        },
      ],
    })
    renderRoom()
    const list = await screen.findByRole('navigation', { name: '면접 지원자' })
    const buttons = await within(list).findAllByRole('button')
    expect(buttons[0]).toHaveTextContent('김하늘')
    expect(buttons[0]).toHaveAttribute('aria-current', 'true')
    expect(buttons[1]).toHaveTextContent('박서준')
    await vi.waitFor(() => expect(requests).toContain('GET /api/interviewer/sessions/s1/a1'))
    expect(requests).not.toContain('GET /api/interviewer/sessions/s1/a0')
  })

  it('상대가 준비 완료했으면 내 [준비 완료]로 확인 창 없이 바로 시작한다', async () => {
    const { posts } = mockServer()
    renderRoom()
    expect(await screen.findByLabelText('원장 재설계에서 직접 정한 부분은? 답변')).toBeDisabled()
    expect(screen.queryByRole('button', { name: '면접 입장' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '면접 시작' })).not.toBeInTheDocument()
    expect(screen.getAllByText(/최인사/).length).toBeGreaterThan(0)
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '준비 완료' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '준비 완료' }))
    expect(await screen.findByRole('button', { name: '면접 종료' })).toBeInTheDocument()
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(posts).toEqual(['POST /api/interviewer/sessions/s1/a1/ready'])
    expect(screen.getByLabelText('원장 재설계에서 직접 정한 부분은? 답변')).toBeEnabled()
    expect(screen.getByText('일정을 두고 조율했다')).toBeInTheDocument()
    expect(
      screen.getByText('김하늘 님의 본인 역할을 확인할 질문 하나 더 만들어줘'),
    ).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '내 메모' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '의견 이유' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /인사.*실무 공유 기록/ })).not.toBeInTheDocument()
  })

  it('상대가 준비 전이면 준비 완료한 채 기다리고, 시작 전에는 취소할 수 있다', async () => {
    const { posts } = mockServer({ otherReady: false })
    renderRoom()
    const people = await screen.findByRole('list', { name: '배정 면접관 접속 현황' })
    await vi.waitFor(() => expect(people).toHaveTextContent('인사 최인사준비 전'))
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '준비 완료' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '준비 완료' }))
    expect(await screen.findByRole('button', { name: '준비 취소' })).toBeInTheDocument()
    expect(people).toHaveTextContent('실무 김실무 (나)준비 완료')
    expect(screen.getByText(/다른 면접관이 준비 완료하면 바로 면접이 시작돼요/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '면접 종료' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '준비 취소' }))
    expect(await screen.findByRole('button', { name: '준비 완료' })).toBeInTheDocument()
    expect(posts).toEqual([
      'POST /api/interviewer/sessions/s1/a1/ready',
      'DELETE /api/interviewer/sessions/s1/a1/ready',
    ])
  })

  it('준비 완료한 다른 면접관의 접속이 끊겼으면 내가 준비 완료해도 시작하지 않는다', async () => {
    mockServer({ otherOnline: false })
    renderRoom()
    expect(await screen.findByText('접속 끊김')).toBeInTheDocument()
    await vi.waitFor(() => expect(screen.getByRole('button', { name: '준비 완료' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: '준비 완료' }))
    expect(await screen.findByRole('button', { name: '준비 취소' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '면접 종료' })).not.toBeInTheDocument()
  })

  it('질문 담당이 비어 있으면 채용 담당자에게 요청하도록 안내하고 준비 완료를 막는다', async () => {
    mockServer({ unassigned: true })
    renderRoom()
    expect(await screen.findByText(/담당 지정을 요청/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '준비 완료' })).toBeDisabled()
  })

  it('종료 확인 후 마지막 답변 저장이 끝나야 종료 API를 호출한다', async () => {
    const { posts, requests, releaseAnswer } = mockServer({
      status: 'IN_PROGRESS',
      ready: true,
      holdAnswer: true,
    })
    renderRoom()
    const answer = await screen.findByLabelText('원장 재설계에서 직접 정한 부분은? 답변')
    fireEvent.change(answer, { target: { value: '마지막으로 남긴 답변' } })
    fireEvent.click(screen.getByRole('button', { name: '면접 종료' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('답변이 없는 내 질문 1개')
    fireEvent.click(within(dialog).getByRole('button', { name: '저장하고 종료' }))
    await vi.waitFor(() =>
      expect(requests).toContain('PUT /api/interviewer/sessions/s1/questions/q1/answer'),
    )
    expect(posts).not.toContain('/api/interviewer/sessions/s1/a1/end')
    expect(answer).toBeDisabled()
    await act(() => Promise.resolve().then(releaseAnswer))
    await vi.waitFor(() => expect(posts).toContain('/api/interviewer/sessions/s1/a1/end'))
    expect(await screen.findByText(/면접이 끝났어요/)).toBeInTheDocument()
  })

  it('자동 저장 중 새로 쓴 답변도 저장한 뒤 종료한다', async () => {
    const { posts, requests, releaseAnswer, savedAnswers } = mockServer({
      status: 'IN_PROGRESS',
      ready: true,
      holdAnswer: true,
    })
    renderRoom()
    const answer = await screen.findByLabelText('원장 재설계에서 직접 정한 부분은? 답변')
    fireEvent.change(answer, { target: { value: '먼저 쓴 답변' } })
    await vi.waitFor(
      () => expect(requests).toContain('PUT /api/interviewer/sessions/s1/questions/q1/answer'),
      { timeout: 3000 },
    )
    fireEvent.change(answer, { target: { value: '저장 중 새로 쓴 답변' } })
    fireEvent.click(screen.getByRole('button', { name: '면접 종료' }))
    fireEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: '저장하고 종료' }),
    )
    expect(posts).not.toContain('/api/interviewer/sessions/s1/a1/end')
    expect(savedAnswers).toEqual([])
    await act(() => Promise.resolve().then(releaseAnswer))
    await vi.waitFor(() => expect(posts).toContain('/api/interviewer/sessions/s1/a1/end'))
    expect(savedAnswers).toEqual(['먼저 쓴 답변', '저장 중 새로 쓴 답변'])
    expect(screen.getByText('저장 중 새로 쓴 답변')).toBeInTheDocument()
  })

  it('마지막 답변을 저장하지 못하면 종료하지 않고 초안을 보존한다', async () => {
    const { posts, requests } = mockServer({
      status: 'IN_PROGRESS',
      ready: true,
      failAnswer: true,
    })
    renderRoom()
    const answer = await screen.findByLabelText('원장 재설계에서 직접 정한 부분은? 답변')
    fireEvent.change(answer, { target: { value: '보존할 마지막 답변' } })
    fireEvent.click(screen.getByRole('button', { name: '면접 종료' }))
    fireEvent.click(
      within(await screen.findByRole('alertdialog')).getByRole('button', { name: '저장하고 종료' }),
    )
    await vi.waitFor(() =>
      expect(requests).toContain('PUT /api/interviewer/sessions/s1/questions/q1/answer'),
    )
    expect(await screen.findByText('저장하지 못했어요')).toBeInTheDocument()
    expect(answer).toHaveValue('보존할 마지막 답변')
    expect(answer).toBeEnabled()
    expect(posts).not.toContain('/api/interviewer/sessions/s1/a1/end')
  })

  it('결과가 확정된 전형에서는 의견을 읽기만 한다', async () => {
    mockServer({ status: 'ENDED', ready: true, stageActive: false })
    renderRoom()
    expect(await screen.findByRole('radio', { name: '추천' })).toBeDisabled()
    expect(screen.getByLabelText('의견 이유')).toBeDisabled()
  })
})
