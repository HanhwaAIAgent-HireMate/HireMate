import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewAssign } from '@/features/interview/InterviewAssign'

function mockServer(assigned: boolean) {
  const puts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      if (typeof input === 'string')
        return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' })
      const url = new URL(input.url).pathname
      if (url === '/api/companies/current/interview-members')
        return Response.json([
          { memberId: 'hr1', name: '최은영', email: 'hr@x', accountRole: 'HR' },
          { memberId: 'kim', name: '김지민', email: 'kim@x', accountRole: 'INTERVIEWER' },
        ])
      if (url.endsWith('/interview/session')) {
        if (input.method === 'PUT') {
          const body: unknown = await input.clone().json()
          puts.push(body)
          return Response.json({ ...(body as object), status: 'SCHEDULED', version: 1 })
        }
        return assigned
          ? Response.json({
              hrMemberId: 'hr1',
              practicalMemberId: 'kim',
              status: 'IN_PROGRESS',
              version: 3,
            })
          : Response.json({ code: 'INTERVIEW_SESSION_NOT_FOUND' }, { status: 404 })
      }
      return Response.json({}, { status: 404 })
    }),
  )
  return puts
}

const renderAssign = () =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <InterviewAssign stageId="s1" applicationId="a1" editable />
      </MemoryRouter>
    </QueryClientProvider>,
  )

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InterviewAssign', () => {
  it('인사 · 실무 면접관을 서로 다른 계정으로 골라 배정한다', async () => {
    const puts = mockServer(false)
    renderAssign()

    fireEvent.click(await screen.findByRole('button', { name: /면접관 배정/ }))
    await screen.findAllByRole('option', { name: '김지민 (면접관)' })
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'kim' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: '실무 면접관' }), {
      target: { value: 'kim' },
    })
    expect(screen.getByRole('button', { name: '서로 다른 계정을 골라 주세요' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'hr1' },
    })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))

    await vi.waitFor(() =>
      expect(puts).toEqual([
        { hrMemberId: 'hr1', practicalMemberId: 'kim', expectedVersion: null },
      ]),
    )
  })

  it('면접이 시작된 지원자는 배정을 바꿀 수 없다', async () => {
    mockServer(true)
    renderAssign()

    expect(await screen.findByText('면접 진행 중')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /인사 최은영 · 실무 김지민/ }))
    expect(screen.getByText('면접이 시작돼 배정을 바꿀 수 없어요.')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '인사 면접관' })).toBeDisabled()
  })
})
