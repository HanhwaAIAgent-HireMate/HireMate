import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import type { StageOverview } from '@/features/screening/api'
import { StageBar } from '@/features/screening/StageBar'

const overview = (stageId: string, type: string, status = 'PENDING') =>
  ({
    stageId,
    recruitmentId: 'r1',
    type,
    status,
    hasScores: false,
    steps: [],
    counts: { pending: 3, pass: 4, fail: 0 },
  }) as unknown as StageOverview

function renderBar(stage: StageOverview) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: Request | string) => {
      if (typeof input === 'string')
        return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
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
  const bar = (value: StageOverview) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StageBar overview={value} />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const view = render(bar(stage))
  return { ...view, rerenderBar: (value: StageOverview) => view.rerender(bar(value)) }
}

afterEach(() => vi.unstubAllGlobals())

it('면접 전형은 결정 현황 왼쪽에 [면접관 배정]을 둔다', async () => {
  const { container } = renderBar(overview('s1', 'INTERVIEW'))
  const button = await screen.findByRole('button', { name: '면접관 배정' })
  const pending = screen.getByText('미결정')
  expect(button.compareDocumentPosition(pending) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(container.querySelector('section')).toBeNull()
})

it('서류 전형에는 면접관 배정을 두지 않는다', () => {
  renderBar(overview('s1', 'DOCUMENT', 'ACTIVE'))
  expect(screen.getByText('미결정')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /면접관/ })).not.toBeInTheDocument()
})

it('다른 면접 전형으로 이동하면 열려 있던 면접관 설정과 선택값을 비운다', async () => {
  const { rerenderBar } = renderBar(overview('s1', 'INTERVIEW'))
  fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
  await screen.findAllByRole('option', { name: '최인사 (hr@x)' })
  fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
    target: { value: 'hr' },
  })
  fireEvent.change(screen.getByRole('combobox', { name: '실무 면접관' }), {
    target: { value: 'practical' },
  })

  rerenderBar(overview('s2', 'INTERVIEW'))

  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
  expect(screen.getByRole('combobox', { name: '인사 면접관' })).toHaveValue('')
  expect(screen.getByRole('combobox', { name: '실무 면접관' })).toHaveValue('')
})
