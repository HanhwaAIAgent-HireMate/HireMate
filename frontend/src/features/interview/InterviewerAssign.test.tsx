import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewerAssign } from '@/features/interview/InterviewerAssign'
import type { StageOverview } from '@/features/screening/api'

const overview = { stageId: 's1', status: 'ACTIVE', type: 'INTERVIEW' } as StageOverview

function mockServer() {
  const requests: { method: string; url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: Request | string) => {
      // CSRF 토큰은 문자열 주소로 부른다
      if (typeof input === 'string')
        return Response.json({ token: 't', headerName: 'X-CSRF-TOKEN', parameterName: '_csrf' })
      const body: unknown = input.method === 'GET' ? null : await input.clone().json()
      requests.push({ method: input.method, url: input.url, body })
      if (input.url.endsWith('/api/auth/me'))
        return Response.json({ memberId: 'hr1', name: '최은영', email: 'hr@x', role: 'HR' })
      if (input.url.endsWith('/api/companies/me/interviewers'))
        return Response.json([{ memberId: 'kim', name: '김지민', email: 'kim@x' }])
      if (input.url.endsWith('/api/stages/s1/interviewers')) {
        if (input.method === 'PUT')
          return Response.json({
            slots: [
              { role: 'HR', memberId: 'hr1', name: '최은영' },
              { role: 'PRACTICAL', memberId: 'kim', name: '김지민' },
            ],
          })
        return Response.json({ slots: [{ role: 'PRACTICAL', memberId: 'kim', name: '김지민' }] })
      }
      return Response.json({}, { status: 404 })
    }),
  )
  return requests
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('InterviewerAssign', () => {
  it('지정된 면접관을 버튼에 보이고, 인사 · 실무를 골라 저장한다', async () => {
    const requests = mockServer()
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter>
          <InterviewerAssign overview={overview} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    fireEvent.click(await screen.findByRole('button', { name: /실무 김지민/ }))
    expect(screen.getByRole('combobox', { name: '실무 면접관' })).toHaveValue('kim')
    await screen.findAllByRole('option', { name: '최은영 (나)' })
    fireEvent.change(screen.getByRole('combobox', { name: '인사 면접관' }), {
      target: { value: 'hr1' },
    })
    fireEvent.click(screen.getByRole('button', { name: '저장' }))

    await vi.waitFor(() =>
      expect(requests.find((request) => request.method === 'PUT')?.body).toEqual({
        slots: [
          { role: 'HR', memberId: 'hr1' },
          { role: 'PRACTICAL', memberId: 'kim' },
        ],
      }),
    )
  })
})
