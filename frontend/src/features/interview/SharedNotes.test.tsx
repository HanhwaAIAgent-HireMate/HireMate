import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { SharedNotes } from './SharedNotes'

afterEach(() => vi.unstubAllGlobals())

it('HR 메모 열기에서 인사·실무 기록을 작성자와 시간별로 읽기 전용 표시한다', async () => {
  const fetcher = vi.fn((input: Request) => {
    expect(input.url).toContain('/api/stages/s/candidates/a/interview/shared-notes')
    return Promise.resolve(
      Response.json([
        {
          memberId: 'hr',
          name: '인사 담당자',
          role: 'HR',
          text: '인사 공유 기록 본문',
          version: 1,
          updatedAt: '2026-11-01T00:00:00Z',
          mine: false,
        },
        {
          memberId: 'dev',
          name: '실무 담당자',
          role: 'PRACTICAL',
          text: '실무 공유 기록 본문',
          version: 1,
          updatedAt: '2026-11-01T00:00:00Z',
          mine: false,
        },
      ]),
    )
  })
  vi.stubGlobal('fetch', fetcher)
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SharedNotes stageId="s" applicationId="a" />
    </QueryClientProvider>,
  )
  expect(fetcher).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /공유 기록 보기/ }))
  await screen.findByText('인사 공유 기록 본문')
  expect(screen.getByText('실무 공유 기록 본문')).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '인사 공유 기록' })).toBeInTheDocument()
  expect(screen.getByRole('heading', { name: '실무 공유 기록' })).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(fetcher).toHaveBeenCalledTimes(1)
})
