import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { createMemoryRouter, Link, MemoryRouter, RouterProvider } from 'react-router'
import { toast } from 'sonner'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { postingKeys, type Posting, type PublicPosting } from '@/features/posting/api'
import { CareersPosting } from '@/features/posting/CareersPosting'
import { posterBrandKey } from '@/features/posting/poster-api'
import { initialPoster, type PosterDesign } from '@/features/posting/poster-design'
import { resetCsrf } from '@/lib/api/client'
import * as thumbnail from '@/features/posting/PosterThumbnail'
import { PostingEditorPage } from '@/pages/hr/PostingEditorPage'
import { PostingPosterPage } from '@/pages/hr/PostingPosterPage'

// 편집기 내부 저장은 기존 동작이며, 여기서는 저장 이후의 형식 선택과 이동을 검사한다.
vi.mock('@/features/posting/PostingEditor', () => ({
  PostingEditor: ({ onNext }: { onNext: () => void }) => <button onClick={onNext}>다음</button>,
}))

const posting: Posting = {
  postingId: 'posting-1',
  recruitmentId: 'recruitment-1',
  companyName: '테스트 기업',
  status: 'DRAFT',
  content: {
    title: '마케팅 신입 채용',
    jobCategory: '마케팅',
    career: '신입',
    employmentType: '정규직',
    location: '서울',
    intro: '회사를 소개합니다.',
    duties: ['마케팅 캠페인 운영'],
    qualifications: ['마케팅 기초 지식'],
    preferred: [],
    benefits: ['교육 지원'],
    roles: [],
    blind: false,
    headcount: 3,
    position: '',
    education: '',
    workHours: '',
    salary: '',
  },
  notices: ['지원 내용을 확인해 주세요.'],
  stages: [],
  documents: [],
  openAt: '2026-11-01T00:00:00Z',
  closeAt: '2026-12-01T00:00:00Z',
  publishedAt: null,
  closedAt: null,
  suggestion: null,
  poster: { ...initialPoster(), enabled: true, color: '#116644' },
  required: { qualifications: [], preferred: [] },
}

beforeEach(() => {
  resetCsrf()
  sessionStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal(
    'ResizeObserver',
    class {
      observe() {}
      disconnect() {}
    },
  )
})
afterEach(() => vi.unstubAllGlobals())

function editor(fail = false) {
  const saved: PosterDesign[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && input.method === 'PUT') {
      const design = (await input.json()) as PosterDesign
      saved.push(design)
      return fail
        ? Response.json({ code: 'SAVE_FAILED' }, { status: 500 })
        : Response.json({ ...posting, poster: design })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  query.setQueryData(posterBrandKey, {})
  const router = createMemoryRouter(
    [
      { path: '/hr/recruitments/:recruitmentId/posting', element: <PostingEditorPage /> },
      { path: '/hr/recruitments/:recruitmentId/posting/:step', element: <p>다음 화면</p> },
    ],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: '다음' }))
  return { router, saved }
}

describe('게시 형식 선택', () => {
  it.each([
    ['글 공고 선택', false, 'publish'],
    ['포스터 공고 선택', true, 'poster'],
  ] as const)('%s을 저장한 뒤 해당 단계로 이동한다', async (label, enabled, step) => {
    const { router, saved } = editor()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '선택' })).toBeDisabled()
    expect(screen.getAllByText(posting.content.title)).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: label }))
    fireEvent.click(screen.getByRole('button', { name: '선택' }))
    await waitFor(() => expect(router.state.location.pathname).toMatch(new RegExp(`/${step}$`)))
    expect(saved).toEqual([{ ...posting.poster, enabled }])
  })

  it('취소하면 이동하거나 저장하지 않는다', () => {
    const { router, saved } = editor()
    fireEvent.click(screen.getByRole('button', { name: '취소' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(router.state.location.pathname).toMatch(/\/posting$/)
    expect(saved).toEqual([])
  })

  it('형식 저장이 실패하면 선택 창을 유지한다', async () => {
    const { router, saved } = editor(true)
    fireEvent.click(screen.getByRole('button', { name: '글 공고 선택' }))
    fireEvent.click(screen.getByRole('button', { name: '선택' }))
    await waitFor(() => expect(saved).toHaveLength(1))
    await waitFor(() => expect(screen.getByRole('button', { name: '선택' })).toBeEnabled())
    expect(router.state.location.pathname).toMatch(/\/posting$/)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })
})

describe('선택한 형식의 채용 페이지', () => {
  it.each([false, true])('포스터 사용 %s일 때 본문을 중복 표시하지 않는다', (enabled) => {
    const publicPosting: PublicPosting = {
      ...posting,
      openAt: posting.openAt!,
      closeAt: posting.closeAt!,
      state: 'OPEN',
      companyAddress: '서울 본사',
      poster: { ...initialPoster(), enabled },
    }
    const { container } = render(
      <MemoryRouter>
        <CareersPosting posting={publicPosting} applyPath="/apply" />
      </MemoryRouter>,
    )
    expect(container.querySelector('.posting-poster') !== null).toBe(enabled)
    expect(screen.getAllByText(/마케팅 캠페인 운영/)).toHaveLength(1)
    expect(container.querySelector('#company')).toHaveTextContent(posting.content.intro)
    expect(container.querySelector('#benefits')).toHaveTextContent('교육 지원')
    expect(screen.queryByRole('button', { name: 'PDF 내보내기' }) !== null).toBe(enabled)
    expect(screen.getByRole('link', { name: '지원하기' })).toHaveAttribute('href', '/apply')
  })
})

it('포스터 대화를 지우면 복구 기록과 다음 요청의 대화는 비우고 디자인은 유지한다', async () => {
  const key = `hiremate:posting:${posting.recruitmentId}:poster-chat`
  sessionStorage.setItem(
    key,
    JSON.stringify({
      baseline: '[]',
      value: [
        { role: 'USER', text: '이전 요청', design: null, recommendations: [] },
        { role: 'ASSISTANT', text: '이전 답변', design: null, recommendations: [] },
      ],
    }),
  )
  let request: { history: unknown[]; design: PosterDesign } | undefined
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && url.endsWith('/ai-requests')) {
      request = (await input.json()) as { history: unknown[]; design: PosterDesign }
      return Response.json({ reply: '새 답변', recommendations: [] })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  query.setQueryData(posterBrandKey, {})
  const router = createMemoryRouter(
    [{ path: '/hr/recruitments/:recruitmentId/posting/poster', element: <PostingPosterPage /> }],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting/poster`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  expect(screen.getByText('이전 답변')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '대화 지우기' }))
  expect(screen.queryByText('이전 답변')).not.toBeInTheDocument()
  expect(screen.queryByText('이전 요청')).not.toBeInTheDocument()
  expect(sessionStorage.getItem(key)).toBeNull()
  expect(screen.getByLabelText('대표 색상')).toHaveValue(posting.poster!.color)
  fireEvent.click(screen.getByRole('button', { name: '우리는 더 고급스러운 느낌이 있어야 해' }))
  await screen.findByText('새 답변')
  expect(request?.history).toEqual([])
  expect(request?.design).toEqual(posting.poster)
})

it('대표 색상은 추가 템플릿 미리보기에도 반영하며 선택 시 다시 원래 색으로 돌아가지 않는다', () => {
  const preview = vi
    .spyOn(thumbnail, 'PosterThumbnail')
    .mockImplementation(({ design }) => (
      <span data-testid="template-preview" data-color={design.color} />
    ))
  try {
    const query = new QueryClient({
      defaultOptions: { queries: { staleTime: Infinity, retry: false } },
    })
    query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
    const template = {
      id: 'own',
      name: '생성템플릿1',
      template: 'CLASSIC',
      color: '#082858',
      decoration: 1,
      canvasJson: null,
    }
    query.setQueryData(posterBrandKey, { templates: [template] })
    const router = createMemoryRouter(
      [{ path: '/hr/recruitments/:recruitmentId/posting/poster', element: <PostingPosterPage /> }],
      { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting/poster`] },
    )
    render(
      <QueryClientProvider client={query}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    )
    fireEvent.change(screen.getByLabelText('대표 색상'), { target: { value: '#7c3aed' } })
    for (const item of screen.getAllByTestId('template-preview'))
      expect(item).toHaveAttribute('data-color', '#7c3aed')
    fireEvent.click(screen.getByRole('button', { name: /^생성템플릿1$/ }))
    expect(screen.getByLabelText('대표 색상')).toHaveValue('#7c3aed')
    expect(template.color).toBe('#082858')
  } finally {
    preview.mockRestore()
  }
})

it('생성 제안은 적용할 때만 새 이름의 템플릿으로 추가하며 공고 저장은 실행하지 않는다', async () => {
  const canvas = JSON.stringify({
    width: 600,
    height: 900,
    source: {
      id: 'generated:00000000-0000-0000-0000-000000000001',
      name: '생성 디자인',
      url: 'hiremate:generated',
      license: 'AI 생성',
    },
    objects: [
      {
        type: 'Textbox',
        hmId: 'title',
        binding: 'title',
        text: '',
        left: 40,
        top: 60,
        width: 500,
        fontSize: 40,
      },
    ],
  })
  const design = { ...posting.poster!, canvasJson: canvas }
  let added: { name: string; canvasJson: string } | undefined
  let brand = {
    template: 'CLASSIC',
    color: '#116644',
    templates: [] as { id: string; name: string; canvasJson: string }[],
  }
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && url.endsWith('/ai-requests'))
      return Response.json({
        reply: '새 양식을 생성했어요',
        recommendations: [{ design, reason: '새 배치를 설계합니다.' }],
      })
    if (
      input instanceof Request &&
      input.method === 'POST' &&
      url.endsWith('/poster-brand/templates')
    ) {
      added = (await input.json()) as { name: string; canvasJson: string }
      brand = { ...brand, templates: [{ ...added, id: 'new-template' }] }
      return Response.json(brand)
    }
    if (url.endsWith('/poster-brand')) return Response.json(brand)
    throw new Error(`Unexpected request: ${url}`)
  })
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false } },
  })
  query.setQueryData(postingKeys.posting(posting.recruitmentId), posting)
  query.setQueryData(posterBrandKey, brand)
  const router = createMemoryRouter(
    [{ path: '/hr/recruitments/:recruitmentId/posting/poster', element: <PostingPosterPage /> }],
    { initialEntries: [`/hr/recruitments/${posting.recruitmentId}/posting/poster`] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: '새로운 포스터 템플릿 2개 만들어줘' }))
  await screen.findByText('새 양식을 생성했어요')
  expect(added).toBeUndefined()
  expect(screen.getByText('생성템플릿1')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '적용' }))
  await waitFor(() => expect(added?.name).toBe('생성템플릿1'))
  expect(JSON.parse(added!.canvasJson)).toHaveProperty('source.name', '생성템플릿1')
  expect(query.getQueryData(postingKeys.posting(posting.recruitmentId))).toEqual(posting)
})

function posterScreen(
  current = posting,
  templates: {
    id: string
    name: string
    template: 'CLASSIC'
    mood: 'TRUST'
    color: string
    decoration: number
    canvasJson: string
  }[] = [],
) {
  const query = new QueryClient({
    defaultOptions: { queries: { staleTime: Infinity, retry: false }, mutations: { retry: false } },
  })
  query.setQueryData(postingKeys.posting(current.recruitmentId), current)
  query.setQueryData(posterBrandKey, {
    template: 'PREMIUM',
    mood: 'PREMIUM',
    color: '#79634b',
    decoration: 0,
    logoFileId: null,
    templates,
  })
  const path = `/hr/recruitments/${current.recruitmentId}/posting/poster`
  const router = createMemoryRouter(
    [
      {
        path: '/hr/recruitments/:recruitmentId/posting/poster',
        element: (
          <>
            <Link to="/hr/settings">설정으로 이동</Link>
            <PostingPosterPage />
          </>
        ),
      },
      { path: '/hr/settings', element: <p>설정 화면</p> },
    ],
    { initialEntries: [path] },
  )
  render(
    <QueryClientProvider client={query}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  )
  return { query, router }
}

it('아이콘 제안을 가운데서 즉시 강조하고 되돌리면 원본을, 적용하면 새 그림을 유지한다', async () => {
  const current: Posting = {
    ...posting,
    stages: [{ id: 'stage-2', name: '2차 면접', type: 'INTERVIEW', status: null, icon: null }],
  }
  const changed = { ...current.poster!, stageIcons: { '2차 면접': 'MESSAGES' as const } }
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && url.endsWith('/ai-requests')) {
      await input.json()
      return Response.json({
        reply: '다른 아이콘 제안',
        recommendations: [{ design: changed, reason: '대화 아이콘으로 제안해요.' }],
      })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  const { query } = posterScreen(current)
  const request = () => {
    fireEvent.change(screen.getByRole('textbox', { name: '수정할 내용' }), {
      target: { value: '2차면접 아이콘 다른걸로 바꿔줘' },
    })
    fireEvent.click(screen.getByRole('button', { name: '보내기' }))
  }
  request()
  const preview = await screen.findByLabelText('2차 면접 아이콘 수정안')
  expect(preview).toHaveAttribute('data-poster-highlight', 'true')
  expect(preview.querySelector('[data-stage-icon]')).toHaveAttribute('data-stage-icon', 'MESSAGES')
  expect(screen.queryByRole('button', { name: '미리보기' })).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '되돌리기' }))
  expect(screen.queryByLabelText('2차 면접 아이콘 수정안')).not.toBeInTheDocument()
  request()
  await screen.findByLabelText('2차 면접 아이콘 수정안')
  fireEvent.click(screen.getByRole('button', { name: '적용' }))
  expect(screen.queryByLabelText('2차 면접 아이콘 수정안')).not.toBeInTheDocument()
  const process = screen.getByRole('list', { name: '전형 절차' })
  expect(process.querySelector('[data-stage-icon]')).toHaveAttribute('data-stage-icon', 'MESSAGES')
  expect(query.getQueryData(postingKeys.posting(posting.recruitmentId))).toEqual(current)
})

it('다른 페이지로 이동하면 실제 임시 저장 성공 후에만 이동하고 공통 성공 알림을 띄운다', async () => {
  const success = vi.spyOn(toast, 'success')
  const failure = vi.spyOn(toast, 'error')
  const writes: PosterDesign[] = []
  let release = () => {}
  const gate = new Promise<void>((resolve) => {
    release = resolve
  })
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && input.method === 'PUT') {
      const design = (await input.json()) as PosterDesign
      writes.push(design)
      await gate
      return Response.json({ ...posting, poster: design })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  try {
    const { router } = posterScreen()
    fireEvent.click(screen.getByRole('button', { name: /^매거진형/ }))
    fireEvent.click(screen.getByRole('link', { name: '설정으로 이동' }))
    await waitFor(() => expect(writes).toHaveLength(1))
    expect(screen.queryByText('설정 화면')).not.toBeInTheDocument()
    expect(success).not.toHaveBeenCalled()
    release()
    await waitFor(() =>
      expect(success.mock.calls, JSON.stringify(failure.mock.calls)).toHaveLength(1),
    )
    await waitFor(() =>
      expect(
        router.state.location.pathname,
        JSON.stringify({ errors: failure.mock.calls, blockers: [...router.state.blockers] }),
      ).toBe('/hr/settings'),
    )
    expect(writes[0].template).toBe('EDITORIAL')
    expect(success).toHaveBeenCalledExactlyOnceWith('임시 저장했어요.')
    expect(sessionStorage.getItem(`hiremate:posting:${posting.recruitmentId}:poster`)).toBeNull()
  } finally {
    release()
    success.mockRestore()
    failure.mockRestore()
  }
})

it('수동 임시 저장도 같은 알림을 쓰고 저장 후 이동할 때 중복 저장하지 않는다', async () => {
  const success = vi.spyOn(toast, 'success')
  const writes: PosterDesign[] = []
  vi.stubGlobal('fetch', async (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf')) return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
    if (input instanceof Request && input.method === 'PUT') {
      const design = (await input.json()) as PosterDesign
      writes.push(design)
      return Response.json({ ...posting, poster: design })
    }
    throw new Error(`Unexpected request: ${url}`)
  })
  try {
    posterScreen()
    fireEvent.click(screen.getByRole('button', { name: /^심플형/ }))
    fireEvent.click(screen.getByRole('button', { name: '임시 저장' }))
    await waitFor(() => expect(success).toHaveBeenCalledExactlyOnceWith('임시 저장했어요.'))
    fireEvent.click(screen.getByRole('link', { name: '설정으로 이동' }))
    await screen.findByText('설정 화면')
    expect(writes).toHaveLength(1)
  } finally {
    success.mockRestore()
  }
})

it('자동 임시 저장 실패 시 이동하지 않고 수정 내용과 복구본을 유지한다', async () => {
  const success = vi.spyOn(toast, 'success')
  const failure = vi.spyOn(toast, 'error')
  vi.stubGlobal('fetch', (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf'))
      return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
    return Promise.resolve(Response.json({ code: 'SAVE_FAILED' }, { status: 500 }))
  })
  try {
    posterScreen()
    fireEvent.click(screen.getByRole('button', { name: /^매거진형/ }))
    fireEvent.click(screen.getByRole('link', { name: '설정으로 이동' }))
    await waitFor(() => expect(failure).toHaveBeenCalledTimes(1))
    expect(success).not.toHaveBeenCalled()
    expect(screen.queryByText('설정 화면')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^매거진형/ })).toHaveAttribute(
      'aria-pressed',
      'true',
    )
    expect(
      sessionStorage.getItem(`hiremate:posting:${posting.recruitmentId}:poster`),
    ).not.toBeNull()
  } finally {
    success.mockRestore()
    failure.mockRestore()
  }
})

it('선택한 추가 템플릿을 삭제하면 설정에 저장된 심플형과 배색을 선택한다', async () => {
  const canvasJson = JSON.stringify({
    width: 600,
    height: 900,
    source: {
      id: 'generated:00000000-0000-0000-0000-000000000001',
      name: '생성템플릿1',
      url: 'hiremate:generated',
      license: 'AI 생성',
    },
    objects: [
      { type: 'Textbox', binding: 'title', text: '', left: 40, top: 60, width: 500, fontSize: 40 },
    ],
  })
  const custom = {
    id: 'custom',
    name: '생성템플릿1',
    template: 'CLASSIC' as const,
    mood: 'TRUST' as const,
    color: '#082858',
    decoration: 1,
    canvasJson,
  }
  vi.stubGlobal('fetch', (input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    if (url.endsWith('/csrf'))
      return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
    if (input instanceof Request && input.method === 'DELETE')
      return Promise.resolve(
        Response.json({
          template: 'PREMIUM',
          mood: 'PREMIUM',
          color: '#79634b',
          decoration: 0,
          logoFileId: null,
          templates: [],
        }),
      )
    throw new Error(`Unexpected request: ${url}`)
  })
  posterScreen({ ...posting, poster: { ...posting.poster!, canvasJson } }, [custom])
  fireEvent.click(screen.getByRole('button', { name: '생성템플릿1 템플릿 삭제' }))
  fireEvent.click(screen.getByRole('button', { name: '삭제' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  expect(screen.getByRole('button', { name: /^심플형/ })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByLabelText('대표 색상')).toHaveValue('#79634b')
})
