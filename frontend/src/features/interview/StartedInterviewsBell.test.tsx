import { QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { createQueryClient } from '@/app/query-client'
import { StartedInterviewsBell } from '@/features/interview/StartedInterviewsBell'

// jsdom에는 PointerEvent가 없어 clientX를 실어 보낼 수 있게 MouseEvent로 채운다
if (!('PointerEvent' in window)) {
  class PointerEventShim extends MouseEvent {
    pointerId: number
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init)
      this.pointerId = init.pointerId ?? 1
    }
  }
  Object.assign(window, { PointerEvent: PointerEventShim })
}

const started = (applicationId: string, applicantName: string, startedAt: string) => ({
  stageId: 's1',
  applicationId,
  recruitmentId: 'r1',
  recruitmentTitle: '결제 플랫폼 백엔드 개발자',
  stageName: '1차 기술 면접',
  applicantName,
  startedAt,
})

function renderBell(initial: unknown[]) {
  const server = { items: initial }
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(Response.json(server.items))),
  )
  const client = createQueryClient()
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <StartedInterviewsBell memberId="m1" />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { server, client }
}

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('HR 알림: 시작한 면접', () => {
  it('새로 시작한 면접을 종에 세고, 열면 면접 전형으로 가는 알림을 보여 주고, 닫으면 읽은 것으로 둔다', async () => {
    renderBell([
      started('a2', '박서준', '2026-11-02T05:00:00Z'),
      started('a1', '김하늘', '2026-11-02T02:00:00Z'),
    ])
    fireEvent.click(await screen.findByRole('button', { name: '알림 2개' }))

    const link = screen.getByRole('link', { name: /박서준 면접이 시작됐어요/ })
    expect(link).toHaveAttribute('href', '/hr/recruitments/r1/stages/s1')
    expect(link).toHaveTextContent('결제 플랫폼 백엔드 개발자 · 1차 기술 면접')
    expect(screen.getByRole('link', { name: /김하늘 면접이 시작됐어요/ })).toBeInTheDocument()

    fireEvent.keyDown(document.activeElement ?? document.body, { key: 'Escape' })
    expect(await screen.findByRole('button', { name: '알림' })).toBeInTheDocument()
    expect(localStorage.getItem('hiremate:interview-started-seen:m1')).toBe(
      String(Date.parse('2026-11-02T05:00:00Z')),
    )
  })

  it('마지막으로 열어 본 뒤에 시작한 면접만 새 알림으로 센다', async () => {
    localStorage.setItem(
      'hiremate:interview-started-seen:m1',
      String(Date.parse('2026-11-02T03:00:00Z')),
    )
    renderBell([
      started('a2', '박서준', '2026-11-02T05:00:00Z'),
      started('a1', '김하늘', '2026-11-02T02:00:00Z'),
    ])

    expect(await screen.findByRole('button', { name: '알림 1개' })).toBeInTheDocument()
  })

  it('화면을 연 뒤에 새로 시작한 면접은 종 아래에 띄워 보여 주고 잠시 뒤 내린다', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const { server, client } = renderBell([started('a1', '김하늘', '2026-11-02T02:00:00Z')])
    // 처음 받아 온 알림은 띄우지 않고 점만 찍는다
    expect(await screen.findByRole('button', { name: '알림 1개' })).toBeInTheDocument()
    expect(screen.queryByRole('status', { name: '새 알림' })).not.toBeInTheDocument()

    server.items = [
      started('a2', '박서준', '2026-11-02T05:00:00Z'),
      started('a1', '김하늘', '2026-11-02T02:00:00Z'),
    ]
    await act(() => client.refetchQueries())
    const preview = await screen.findByRole('status', { name: '새 알림' })
    expect(preview).toHaveTextContent('박서준 면접이 시작됐어요')
    expect(preview).toHaveTextContent('결제 플랫폼 백엔드 개발자 · 1차 기술 면접')
    expect(preview).not.toHaveTextContent('김하늘')
    expect(within(preview).getByRole('link')).toHaveAttribute(
      'href',
      '/hr/recruitments/r1/stages/s1',
    )

    await act(() => vi.advanceTimersByTimeAsync(8_000))
    expect(screen.queryByRole('status', { name: '새 알림' })).not.toBeInTheDocument()
    // 띄운 알림을 내려도 알림 목록을 열어 보기 전까지 점은 남는다
    expect(screen.getByRole('button', { name: '알림 2개' })).toBeInTheDocument()
  })

  it('띄운 알림을 닫으면 다시 띄우지 않고, 그 뒤에 온 알림만 새로 띄운다', async () => {
    const { server, client } = renderBell([])
    await vi.waitFor(() =>
      expect(client.getQueryState(['interview', 'started'])?.status).toBe('success'),
    )
    server.items = [started('a2', '박서준', '2026-11-02T05:00:00Z')]
    await act(() => client.refetchQueries())
    fireEvent.click(await screen.findByRole('button', { name: '새 알림 닫기' }))
    expect(screen.queryByRole('status', { name: '새 알림' })).not.toBeInTheDocument()

    await act(() => client.refetchQueries())
    expect(screen.queryByRole('status', { name: '새 알림' })).not.toBeInTheDocument()

    server.items = [started('a3', '이도윤', '2026-11-02T06:00:00Z'), ...server.items]
    await act(() => client.refetchQueries())
    const preview = await screen.findByRole('status', { name: '새 알림' })
    expect(preview).toHaveTextContent('이도윤 면접이 시작됐어요')
    expect(preview).not.toHaveTextContent('박서준')
  })

  it('띄운 알림을 오른쪽으로 밀면 닫히고, 조금만 밀면 제자리로 돌아온다', async () => {
    const { server, client } = renderBell([])
    await vi.waitFor(() =>
      expect(client.getQueryState(['interview', 'started'])?.status).toBe('success'),
    )
    server.items = [started('a2', '박서준', '2026-11-02T05:00:00Z')]
    await act(() => client.refetchQueries())
    const preview = await screen.findByRole('status', { name: '새 알림' })

    fireEvent.pointerDown(preview, { clientX: 100, button: 0 })
    fireEvent.pointerMove(preview, { clientX: 130 })
    expect(preview.style.transform).toBe('translateX(30px)')
    fireEvent.pointerUp(preview, { clientX: 130 })
    expect(preview.style.transform).toBe('translateX(0px)')
    expect(screen.getByRole('status', { name: '새 알림' })).toBeInTheDocument()

    // 왼쪽으로는 움직이지 않는다
    fireEvent.pointerDown(preview, { clientX: 100, button: 0 })
    fireEvent.pointerMove(preview, { clientX: 40 })
    expect(preview.style.transform).toBe('translateX(0px)')
    fireEvent.pointerUp(preview, { clientX: 40 })

    fireEvent.pointerDown(preview, { clientX: 100, button: 0 })
    fireEvent.pointerMove(preview, { clientX: 220 })
    fireEvent.pointerUp(preview, { clientX: 220 })
    await vi.waitFor(() =>
      expect(screen.queryByRole('status', { name: '새 알림' })).not.toBeInTheDocument(),
    )
    // 밀어서 닫아도 알림 목록을 열어 보기 전까지 점은 남는다
    expect(screen.getByRole('button', { name: '알림 1개' })).toBeInTheDocument()
  })

  it('시작한 면접이 없으면 새 알림이 없다고 알린다', async () => {
    renderBell([])
    fireEvent.click(await screen.findByRole('button', { name: '알림' }))

    expect(await screen.findByText('새 알림이 없어요.')).toBeInTheDocument()
  })
})
