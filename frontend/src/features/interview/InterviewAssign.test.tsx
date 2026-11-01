import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewAssign } from '@/features/interview/InterviewAssign'

function mockServer({
  assigned = false,
  locked = false,
  started = false,
  assignmentError = '',
} = {}) {
  const puts: { path: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      if (typeof input === 'string')
        return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' })
      const path = new URL(input.url).pathname
      if (path === '/api/companies/current/interview-members')
        return Response.json([
          { memberId: 'choi', name: '최인사', email: 'choi@x', accountRole: 'INTERVIEWER' },
          { memberId: 'kim', name: '김지민', email: 'kim@x', accountRole: 'INTERVIEWER' },
        ])
      if (path === '/api/stages/s1/interview/sessions')
        return Response.json(
          started ? [{ applicationId: 'a2', status: 'IN_PROGRESS', attendees: [] }] : [],
        )
      if (path === '/api/stages/s1/interview/assignment') {
        if (input.method === 'PUT') {
          const body: unknown = await input.clone().json()
          puts.push({ path, body })
          return Response.json({ stageId: 's1', ...(body as object), locked, version: 1 })
        }
        if (assignmentError)
          return Response.json(
            { code: assignmentError },
            { status: assignmentError === 'INTERVIEW_ASSIGNMENT_CONFLICT' ? 409 : 403 },
          )
        return assigned
          ? Response.json({
              stageId: 's1',
              hrMemberId: 'choi',
              practicalMemberId: 'kim',
              locked,
              version: 3,
            })
          : Response.json({ code: 'INTERVIEW_ASSIGNMENT_NOT_FOUND' }, { status: 404 })
      }
      return Response.json({}, { status: 404 })
    }),
  )
  return puts
}

const renderAssign = (editable = true) =>
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <InterviewAssign stageId="s1" editable={editable} />
      </MemoryRouter>
    </QueryClientProvider>,
  )

afterEach(() => vi.unstubAllGlobals())

describe('전형 공통 면접관 배정', () => {
  it('버튼 하나로 전형에 한 번 배정하고 모든 지원자에 공통 적용한다', async () => {
    const puts = mockServer()
    renderAssign()
    fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
    expect(
      screen.getByText('이 전형의 모든 지원자에게 공통으로 적용해요.', { exact: false }),
    ).toBeInTheDocument()
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
    fireEvent.click(screen.getByRole('button', { name: '전형 전체에 적용' }))
    await vi.waitFor(() =>
      expect(puts).toEqual([
        {
          path: '/api/stages/s1/interview/assignment',
          body: { hrMemberId: 'choi', practicalMemberId: 'kim', expectedVersion: null },
        },
      ]),
    )
    await vi.waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
    const button = screen.getByRole('button', { name: '면접관 배정' })
    expect(button).toHaveAttribute('title', '인사 최인사 · 실무 김지민')
    fireEvent.click(button)
    expect(screen.getByRole('combobox', { name: '인사 면접관' })).toHaveValue('choi')
    expect(screen.getByRole('combobox', { name: '실무 면접관' })).toHaveValue('kim')
  })
  it('다른 지원자의 면접이 시작되면 전형 전체 배정을 잠그고 보기만 한다', async () => {
    mockServer({ assigned: true, started: true })
    renderAssign()
    fireEvent.click(await screen.findByRole('button', { name: '면접관 보기' }))
    expect(
      screen.getByText('면접이 시작된 지원자가 있어 면접관을 바꿀 수 없어요.'),
    ).toBeInTheDocument()
    expect(await screen.findByText('최인사')).toBeInTheDocument()
    expect(screen.getByText('김지민')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '전형 전체에 적용' })).not.toBeInTheDocument()
  })
  it('서버가 잠근 공통 배정은 진행 현황을 받기 전에도 수정할 수 없다', async () => {
    mockServer({ assigned: true, locked: true })
    renderAssign()
    expect(await screen.findByRole('button', { name: '면접관 보기' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '면접관 배정' })).not.toBeInTheDocument()
  })
  it('확정된 전형에서는 공통 면접관을 읽기만 한다', async () => {
    mockServer({ assigned: true })
    renderAssign(false)
    fireEvent.click(await screen.findByRole('button', { name: '면접관 보기' }))
    expect(await screen.findByText('최인사')).toBeInTheDocument()
    expect(
      screen.queryByText('면접이 시작된 지원자가 있어 면접관을 바꿀 수 없어요.'),
    ).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
  it('확정된 전형에 배정한 면접관이 없으면 버튼을 두지 않는다', async () => {
    mockServer()
    renderAssign(false)
    await vi.waitFor(() =>
      expect(vi.mocked(fetch).mock.calls.some(([input]) => typeof input !== 'string')).toBe(true),
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
  it('기존 지원자별 배정이 다르면 공통 면접관을 직접 골라 충돌을 해결한다', async () => {
    const puts = mockServer({ assignmentError: 'INTERVIEW_ASSIGNMENT_CONFLICT' })
    renderAssign()
    fireEvent.click(await screen.findByRole('button', { name: '면접관 배정' }))
    expect(screen.getByRole('alert')).toHaveTextContent('기존 지원자별 면접관 배정이 서로 달라요.')
    expect(screen.getByRole('combobox', { name: '인사 면접관' })).toHaveValue('')
    expect(screen.getByRole('combobox', { name: '실무 면접관' })).toHaveValue('')
    await screen.findAllByRole('option', { name: '김지민 (kim@x)' })
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'choi' },
    })
    fireEvent.change(screen.getByRole('combobox', { name: '실무 면접관' }), {
      target: { value: 'kim' },
    })
    fireEvent.click(screen.getByRole('button', { name: '전형 전체에 적용' }))
    await vi.waitFor(() =>
      expect(puts).toEqual([
        {
          path: '/api/stages/s1/interview/assignment',
          body: { hrMemberId: 'choi', practicalMemberId: 'kim', expectedVersion: null },
        },
      ]),
    )
    expect(await screen.findByTitle('인사 최인사 · 실무 김지민')).toHaveAccessibleName(
      '면접관 배정',
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('충돌 상태여도 시작된 면접이 있으면 공통 배정을 새로 정할 수 없다', async () => {
    mockServer({ assignmentError: 'INTERVIEW_ASSIGNMENT_CONFLICT', started: true })
    renderAssign()
    await vi.waitFor(() =>
      expect(screen.queryByRole('button', { name: '면접관 배정' })).not.toBeInTheDocument(),
    )
    fireEvent.click(await screen.findByRole('button', { name: '면접관 보기' }))
    expect(screen.getByRole('alert')).toHaveTextContent('기존 지원자별 면접관 배정이 서로 달라요.')
    expect(screen.queryByRole('button', { name: '전형 전체에 적용' })).not.toBeInTheDocument()
  })
  it('일반 조회 오류에서는 공통 배정을 임의로 새로 저장할 수 없다', async () => {
    mockServer({ assignmentError: 'FORBIDDEN' })
    renderAssign()
    expect(await screen.findByRole('alert')).toHaveTextContent('면접관 배정을 불러오지 못했어요.')
    expect(screen.queryByRole('button', { name: '면접관 배정' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '전형 전체에 적용' })).not.toBeInTheDocument()
  })
})
