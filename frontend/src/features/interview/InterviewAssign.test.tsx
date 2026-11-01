import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewAssign } from '@/features/interview/InterviewAssign'

function mockServer(assigned: boolean, practicalEntered = true) {
  const puts: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      if (typeof input === 'string')
        return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' })
      const url = new URL(input.url).pathname
      if (url === '/api/companies/current/interview-members')
        return Response.json([
          { memberId: 'choi', name: '최인사', email: 'choi@x', accountRole: 'INTERVIEWER' },
          { memberId: 'kim', name: '김지민', email: 'kim@x', accountRole: 'INTERVIEWER' },
        ])
      if (url.endsWith('/interview/sessions'))
        return Response.json([
          {
            applicationId: 'a1',
            status: 'IN_PROGRESS',
            startedAt: '2026-11-01T08:00:00Z',
            endedAt: null,
            attendees: [
              {
                role: 'HR',
                memberId: 'choi',
                name: '최인사',
                entered: true,
                online: true,
                me: false,
              },
              {
                role: 'PRACTICAL',
                memberId: 'kim',
                name: '김지민',
                entered: practicalEntered,
                online: false,
                me: false,
              },
            ],
          },
        ])
      if (url.endsWith('/interview/session')) {
        if (input.method === 'PUT') {
          const body: unknown = await input.clone().json()
          puts.push(body)
          return Response.json({ ...(body as object), status: 'SCHEDULED', version: 1 })
        }
        return assigned
          ? Response.json({
              hrMemberId: 'choi',
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
  it('인사와 실무 면접관을 서로 다른 계정으로 골라 배정한다', async () => {
    const puts = mockServer(false)
    renderAssign()

    fireEvent.click(await screen.findByRole('button', { name: /면접관 배정/ }))
    await screen.findAllByRole('option', { name: '김지민 (kim@x)' })
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'kim' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: '실무 면접관' }), {
      target: { value: 'kim' },
    })
    expect(screen.getByRole('button', { name: '서로 다른 계정을 골라 주세요' })).toBeDisabled()
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'choi' },
    })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))

    await vi.waitFor(() =>
      expect(puts).toEqual([
        { hrMemberId: 'choi', practicalMemberId: 'kim', expectedVersion: null },
      ]),
    )
  })

  it('면접이 시작된 지원자는 배정을 바꿀 수 없다', async () => {
    mockServer(true)
    renderAssign()

    expect(await screen.findByText('면접 진행 중')).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: /인사 최인사, 실무 김지민/ }))
    expect(screen.getByText('면접이 시작돼 배정을 바꿀 수 없어요.')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '인사 면접관' })).toBeDisabled()
  })
})

it('HR 지원자 카드에서 배정된 면접관의 이름과 입장 및 접속 상태를 확인한다', async () => {
  mockServer(true)
  renderAssign()

  const attendance = await screen.findByRole('list', { name: '면접관 입장 상태' })
  const rows = within(attendance).getAllByRole('listitem')
  expect(rows[0]).toHaveTextContent('인사 최인사')
  expect(rows[0]).toHaveTextContent('접속 중')
  expect(rows[1]).toHaveTextContent('실무 김지민')
  expect(rows[1]).toHaveTextContent('접속 끊김')
})

it('면접 입장을 누르지 않은 면접관은 대기로 보인다', async () => {
  mockServer(true, false)
  renderAssign()

  const attendance = await screen.findByRole('list', { name: '면접관 입장 상태' })
  const practical = within(attendance).getAllByRole('listitem')[1]
  expect(practical).toHaveTextContent('실무 김지민')
  expect(practical).toHaveTextContent('입장 대기')
  expect(practical).not.toHaveTextContent('접속 끊김')
})
