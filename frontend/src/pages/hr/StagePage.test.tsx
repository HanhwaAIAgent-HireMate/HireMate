import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { StagePage } from './StagePage'

const state = vi.hoisted(() => ({ stageId: 's1', type: 'INTERVIEW', status: 'PENDING' }))
vi.mock('react-resizable-panels', () => ({ useDefaultLayout: () => ({}) }))
vi.mock('@/components/ui/resizable', () => ({
  ResizablePanelGroup: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizablePanel: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  ResizableHandle: () => null,
}))
vi.mock('@/app/header-store', () => ({ useHeaderCrumb: () => {} }))
vi.mock('@/features/screening/store', () => ({ useStageUi: () => ({ reset: () => {} }) }))
vi.mock('@/features/screening/tabs', () => ({
  useCurrentTab: () => ({ tabs: { data: [], isPending: false }, tab: null }),
}))
vi.mock('@/features/screening/api', () => ({
  useStageOverview: () => ({
    data: {
      stageId: state.stageId,
      recruitmentId: 'r1',
      recruitmentTitle: '백엔드 개발자',
      name: '기술 면접',
      recruitmentStatus: 'PUBLISHED',
      postingId: 'p1',
      type: state.type,
      status: state.status,
    },
  }),
}))
vi.mock('@/features/screening/StageHeader', () => ({
  StageStepper: ({ actions }: { actions: ReactNode }) => <header>{actions}</header>,
}))
vi.mock('@/features/screening/StageBar', () => ({ StageBar: () => null }))
vi.mock('@/features/screening/CandidateList', () => ({ CandidateList: () => <p>지원자 목록</p> }))

function renderStage() {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request) => {
      const path = new URL(input.url).pathname
      if (path === '/api/companies/current/interview-members')
        return Promise.resolve(
          Response.json([
            { memberId: 'hr', name: '최인사', email: 'hr@x', accountRole: 'INTERVIEWER' },
            {
              memberId: 'practical',
              name: '김실무',
              email: 'practical@x',
              accountRole: 'INTERVIEWER',
            },
          ]),
        )
      if (path.endsWith('/interview/sessions')) return Promise.resolve(Response.json([]))
      return Promise.resolve(
        Response.json({ code: 'INTERVIEW_ASSIGNMENT_NOT_FOUND' }, { status: 404 }),
      )
    }),
  )
  const client = createQueryClient()
  const page = () => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StagePage />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const view = render(page())
  return { ...view, rerenderStage: () => view.rerender(page()) }
}

afterEach(() => {
  vi.unstubAllGlobals()
  state.stageId = 's1'
  state.type = 'INTERVIEW'
  state.status = 'PENDING'
})

it('지원자 카드와 Chat 탭이 없는 시작 전 면접에도 공통 설정을 한 번 표시한다', async () => {
  renderStage()
  expect(await screen.findByRole('button', { name: '면접관 배정' })).toBeInTheDocument()
  expect(screen.getAllByRole('region', { name: '전형 면접관' })).toHaveLength(1)
  expect(
    screen.getByText('전형을 시작하면 선택 지원자와 AI Chat을 쓸 수 있어요.'),
  ).toBeInTheDocument()
})

it('서류 전형에는 면접관 배정을 표시하지 않는다', () => {
  state.type = 'DOCUMENT'
  renderStage()
  expect(screen.queryByRole('region', { name: '전형 면접관' })).not.toBeInTheDocument()
})

it('다른 면접 전형으로 이동하면 열려 있던 면접관 설정과 선택값을 비운다', async () => {
  const { rerenderStage } = renderStage()
  fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
  await screen.findAllByRole('option', { name: '최인사 (hr@x)' })
  fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
    target: { value: 'hr' },
  })
  fireEvent.change(screen.getByRole('combobox', { name: '실무 면접관' }), {
    target: { value: 'practical' },
  })

  state.stageId = 's2'
  rerenderStage()

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
  expect(screen.getByRole('combobox', { name: '인사 면접관' })).toHaveValue('')
  expect(screen.getByRole('combobox', { name: '실무 면접관' })).toHaveValue('')
})
