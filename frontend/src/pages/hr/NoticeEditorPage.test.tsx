import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import type { Notice } from '@/features/notice/api'

import { NoticeEditorPage } from './NoticeEditorPage'

const overview = {
  stageId: 's1',
  recruitmentId: 'r1',
  recruitmentTitle: '결제 백엔드 개발자',
  recruitmentStatus: 'IN_PROGRESS',
  postingId: 'p1',
  name: '서류 전형',
}

function notice(content: string): Notice {
  return {
    noticeId: 'n1',
    stageId: 's1',
    group: 'PASS',
    templateType: 'NEXT_STAGE',
    label: '합격 안내',
    subject: '[OO핀테크] 서류 전형 결과 안내',
    greeting: '{지원자명}님, 지원해 주셔서 감사합니다.',
    content,
    guide: '',
    guideMissing: [],
    onboarding: { startDate: '', place: '', documents: '', preparation: '', note: '' },
    applicationNoLine: null,
    interviewTimeHint: false,
    closing: '감사합니다.',
    requiredText: '본 메일은 발신 전용입니다.',
    recipientCount: 3,
    status: 'DRAFT',
    sentCount: 0,
    failedCount: 0,
    sentAt: null,
  }
}

/** 응답을 테스트가 정할 때까지 기다리게 하는 요청 */
function pending() {
  let resolve: (response: Response) => void = () => undefined
  const promise = new Promise<Response>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function mockServer(current: Notice, routes: Record<string, () => Promise<Response>>) {
  const fetch = vi.fn((input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    const method = typeof input === 'string' ? 'GET' : input.method
    const path = new URL(url, 'http://localhost').pathname
    if (path === '/api/auth/csrf')
      return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
    if (path === '/api/stages/s1') return Promise.resolve(Response.json(overview))
    if (method === 'GET' && path === '/api/stages/s1/notices')
      return Promise.resolve(Response.json([current]))
    const route = routes[`${method} ${path}`]
    // 다음 면접 배정은 따로 정하지 않으면 끝난 상태다 (합격 안내는 배정한 뒤에 보낸다)
    if (!route && method === 'GET' && path === '/api/stages/s1/interview-scheduling')
      return Promise.resolve(Response.json({ status: 'READY' }))
    return route ? route() : Promise.resolve(Response.json({ code: 'NOT_FOUND' }, { status: 404 }))
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function renderEditor() {
  const router = createMemoryRouter(
    [
      {
        path: '/hr/recruitments/:recruitmentId/stages/:stageId/close/*',
        element: <NoticeEditorPage />,
      },
    ],
    { initialEntries: ['/hr/recruitments/r1/stages/s1/close/notices/PASS'] },
  )
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
}

// 테스트용 브라우저(jsdom)에는 스크롤이 없어서, AI 패널이 대화 끝으로 내릴 때 쓰는 함수를 비워 둔다
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('안내 초안 화면', () => {
  it('AI 초안을 쓰는 동안 쓰고 있다고 보여 주고, 다 쓰면 바로 고칠 수 있다', async () => {
    const draft = pending()
    mockServer(notice(''), { 'POST /api/stages/s1/notices/PASS/prepare': () => draft.promise })
    renderEditor()

    expect(await screen.findByText('AI가 합격 안내 초안을 쓰고 있어요')).toBeInTheDocument()
    draft.resolve(Response.json([notice('서류 전형에 합격하셨습니다.')]))
    expect(await screen.findByLabelText('안내 내용')).toHaveValue('서류 전형에 합격하셨습니다.')
  })

  it('이미 쓴 초안은 다시 쓰지 않는다', async () => {
    const fetch = mockServer(notice('서류 전형에 합격하셨습니다.'), {})
    renderEditor()

    expect(await screen.findByLabelText('안내 내용')).toHaveValue('서류 전형에 합격하셨습니다.')
    const prepared = fetch.mock.calls.some(([input]) =>
      String(input instanceof Request ? input.url : input).includes('/prepare'),
    )
    expect(prepared).toBe(false)
  })

  it('초안을 쓰지 못하면 다시 쓸 수 있게 한다', async () => {
    mockServer(notice(''), {
      'POST /api/stages/s1/notices/PASS/prepare': () =>
        Promise.resolve(Response.json({ code: 'AI_UNAVAILABLE' }, { status: 503 })),
    })
    renderEditor()

    expect(await screen.findByText('초안을 쓰지 못했어요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 쓰기' })).toBeInTheDocument()
  })

  it('메일을 보내는 동안 보내고 있다고 보여 준다', async () => {
    const sending = pending()
    mockServer(notice('서류 전형에 합격하셨습니다.'), {
      'POST /api/stages/s1/notices/PASS/send': () => sending.promise,
    })
    renderEditor()

    // 다음 면접 배정 상태를 확인한 뒤에 보낼 수 있다
    const sendButton = await screen.findByRole('button', { name: '3명에게 발송' })
    await waitFor(() => expect(sendButton).toBeEnabled())
    fireEvent.click(sendButton)
    expect(await screen.findByText('메일을 보내고 있어요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '보내는 중…' })).toBeDisabled()
  })

  it('블라인드 채용이면 붙는 지원번호 안내와, 면접 일정에 붙는 지원자별 시각을 편집 화면에서 알려 준다', async () => {
    mockServer(
      {
        ...notice('서류 전형에 합격하셨습니다.'),
        guide: '■ 1차 면접 안내\n- 일정: 2026년 11월 30일(월)',
        interviewTimeHint: true,
        applicationNoLine: '{지원자명}님의 지원번호는 {지원번호}번입니다.',
      },
      {},
    )
    renderEditor()

    expect(
      await screen.findByText('보낼 때 지원자마다 배정된 면접 시각이 함께 들어가요'),
    ).toBeInTheDocument()
    expect(screen.getByText('{지원자명}님의 지원번호는 {지원번호}번입니다.')).toBeInTheDocument()
  })

  it('다음 면접 시간을 배정하지 않았으면 합격 안내를 보낼 수 없다고 알린다', async () => {
    mockServer(notice('서류 전형에 합격하셨습니다.'), {
      'GET /api/stages/s1/interview-scheduling': () =>
        Promise.resolve(Response.json({ status: 'DATE_REQUIRED' })),
    })
    renderEditor()

    expect(await screen.findByText(/다음 면접 시간을 배정한 뒤 보낼 수 있어요/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '3명에게 발송' })).toBeDisabled()
    expect(screen.getByRole('link', { name: '배정 상태 보기' })).toBeInTheDocument()
  })
})
