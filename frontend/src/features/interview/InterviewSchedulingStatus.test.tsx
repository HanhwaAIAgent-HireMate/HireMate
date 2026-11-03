import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { InterviewSchedulingStatus } from './InterviewSchedulingStatus'

afterEach(() => vi.unstubAllGlobals())

it('배정 실패를 알리고 재시도한 뒤 준비 중 상태에서 완료까지 갱신한다', async () => {
  let status = 'FAILED'
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request | string) => {
      if (typeof request === 'string')
        return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
      if (request.method === 'POST') {
        status = 'READY'
        return Promise.resolve(
          Response.json({ status: 'PENDING', nextStageId: 'next', errorCode: null }),
        )
      }
      return Promise.resolve(
        Response.json({
          status,
          nextStageId: 'next',
          errorCode: status === 'FAILED' ? 'INTERVIEW_SCHEDULE_CAPACITY' : null,
        }),
      )
    }),
  )
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <InterviewSchedulingStatus
          stageId="previous"
          guidesPath="/close/notices/PASS#next-stage-guide"
        />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText(/배정할 시간이 부족해요/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '면접 날짜 정하기' })).toHaveAttribute(
    'href',
    '/close/notices/PASS#next-stage-guide',
  )
  fireEvent.click(screen.getByRole('button', { name: '일정 배정 다시 시도' }))
  expect(await screen.findByText(/배정하고 있어요/)).toBeInTheDocument()
  expect(await screen.findByText(/면접 일정 배정 완료/, {}, { timeout: 3000 })).toBeInTheDocument()
})
