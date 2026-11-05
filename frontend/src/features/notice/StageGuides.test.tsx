import { QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeAll, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { NextStageGuide } from './StageGuides'

// jsdom에는 화면 스크롤이 없다
const scroll = vi.fn()

beforeAll(() => {
  Element.prototype.scrollIntoView = scroll
})

afterEach(() => vi.unstubAllGlobals())

function stubGuides(notifiedCount = 0) {
  vi.stubGlobal(
    'fetch',
    vi.fn((request: Request | string) => {
      if (typeof request === 'string')
        return Promise.resolve(Response.json({ token: 'test', headerName: 'X-CSRF-TOKEN' }))
      return Promise.resolve(
        Response.json([
          {
            stageId: 'interview',
            seq: 2,
            name: '1차 면접',
            guide: { schedule: null, method: null, place: '', preparation: '', note: '' },
            missing: ['일정', '진행 방식', '장소·접속 링크', '준비 사항'],
            notifiedCount,
          },
        ]),
      )
    }),
  )
}

function renderGuide(path: string) {
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter initialEntries={[path]}>
        <NextStageGuide recruitmentId="r1" stageId="interview" editable />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

it('다음 전형 안내는 카드로 펼쳐 두고 비어 있는 칸을 알린다', async () => {
  stubGuides()
  renderGuide('/close')

  expect(await screen.findByRole('heading', { name: '1차 면접 안내' })).toBeInTheDocument()
  expect(screen.getByText(/비어 있음: 일정, 진행 방식/)).toBeInTheDocument()
  expect(screen.getByLabelText('1차 면접 일정')).toBeInTheDocument()
  expect(scroll).not.toHaveBeenCalled()
})

it('안내 메일 화면의 [입력하러 가기](#next-stage-guide)로 오면 이 카드로 내려간다', async () => {
  stubGuides()
  renderGuide('/close#next-stage-guide')

  expect(await screen.findByLabelText('1차 면접 일정')).toBeInTheDocument()
  expect(scroll).toHaveBeenCalled()
})

it('안내 메일을 받은 지원자가 있으면 고칠 수 없고 전화로 알리라고 안내한다', async () => {
  stubGuides(3)
  renderGuide('/close')

  expect(await screen.findByLabelText('1차 면접 일정')).toBeDisabled()
  expect(screen.getByLabelText('1차 면접 준비 사항')).toBeDisabled()
  expect(screen.getByText(/안내 메일을 보내서 고칠 수 없어요/)).toBeInTheDocument()
  expect(screen.getByText('3명에게 보냄')).toBeInTheDocument()
  expect(screen.queryByText(/비어 있음/)).not.toBeInTheDocument()
})
