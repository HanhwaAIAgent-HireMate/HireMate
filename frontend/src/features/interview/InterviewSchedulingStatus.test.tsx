import { QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { useNotices } from '@/features/notice/api'
import { NextStageGuide } from '@/features/notice/StageGuides'
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
        <InterviewSchedulingStatus stageId="previous" guidesPath="/close#next-stage-guide" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText(/배정할 시간이 부족해요/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '다음 전형 안내 확인' })).toHaveAttribute(
    'href',
    '/close#next-stage-guide',
  )
  fireEvent.click(screen.getByRole('button', { name: '일정 배정 다시 시도' }))
  expect(await screen.findByText(/배정하고 있어요/)).toBeInTheDocument()
  expect(await screen.findByText(/면접 일정 배정 완료/, {}, { timeout: 3000 })).toBeInTheDocument()
})

it('날짜 저장 후 배정 상태와 메일 안내를 새로 조회한다', async () => {
  let date: string | null = null
  const savedDate = '2099-11-06'
  vi.stubGlobal(
    'fetch',
    vi.fn(async (request: Request | string) => {
      if (typeof request === 'string')
        return Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' })
      if (request.method === 'PUT') {
        const body = (await request.json()) as { schedule: string }
        date = body.schedule
        return Response.json({})
      }
      if (request.url.includes('stage-guides'))
        return Response.json([
          {
            stageId: 'next',
            seq: 2,
            name: '1차 면접',
            guide: { schedule: date, method: null, place: '', preparation: '', note: '' },
            missing: [],
            notifiedCount: 0,
          },
        ])
      if (request.url.endsWith('/notices'))
        return Response.json([{ group: 'PASS', guide: date ?? '안내 없음' }])
      return Response.json({
        status: date ? 'READY' : 'DATE_REQUIRED',
        nextStageId: 'next',
        errorCode: null,
      })
    }),
  )
  function MailGuide() {
    const notices = useNotices('previous')
    return <p>{notices.data?.[0]?.guide}</p>
  }
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <NextStageGuide recruitmentId="recruitment" stageId="next" editable />
        <InterviewSchedulingStatus stageId="previous" guidesPath="/close#next-stage-guide" />
        <MailGuide />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('안내 없음')).toBeInTheDocument()
  expect(await screen.findByText(/면접 날짜를 설정한 뒤/)).toBeInTheDocument()
  fireEvent.change(await screen.findByLabelText('1차 면접 일정'), { target: { value: savedDate } })
  fireEvent.click(screen.getByRole('button', { name: '안내 저장' }))
  expect(await screen.findByText(/면접 일정 배정 완료/)).toBeInTheDocument()
  expect(await screen.findByText(savedDate)).toBeInTheDocument()
})
