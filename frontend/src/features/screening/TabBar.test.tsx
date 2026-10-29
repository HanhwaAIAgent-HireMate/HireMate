import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { resetCsrf } from '@/lib/api/client'
import type { StageTab } from '@/features/screening/tabs'
import { TabBar } from '@/features/screening/TabBar'

function tab(id: string, name: string, selectedCount = 0): StageTab {
  return { id, name, selectedCount, canRestore: false }
}

function mockServer() {
  const fetch = vi.fn((input: Request | string) => {
    const url = typeof input === 'string' ? input : input.url
    const method = typeof input === 'string' ? 'GET' : input.method
    const path = new URL(url, 'http://localhost').pathname
    if (path === '/api/auth/csrf')
      return Promise.resolve(Response.json({ token: 't', headerName: 'X-CSRF-TOKEN' }))
    if (method === 'POST' && path === '/api/stages/s1/tabs')
      return Promise.resolve(Response.json(tab('t9', '탭 9'), { status: 201 }))
    if (method === 'PATCH') return Promise.resolve(Response.json(tab('t2', '바꾼 이름')))
    if (method === 'DELETE') return Promise.resolve(new Response(null, { status: 204 }))
    return Promise.resolve(Response.json([]))
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}

function sent(fetch: ReturnType<typeof mockServer>, method: string) {
  return fetch.mock.calls
    .map(([input]) => input)
    .filter((input): input is Request => typeof input !== 'string' && input.method === method)
}

function renderBar(tabs: StageTab[], { current = 't1', editable = true } = {}) {
  const onSelect = vi.fn()
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <TabBar stageId="s1" tabs={tabs} current={current} onSelect={onSelect} editable={editable} />
    </QueryClientProvider>,
  )
  return onSelect
}

afterEach(() => {
  resetCsrf()
  vi.unstubAllGlobals()
})

describe('TabBar', () => {
  it('탭 이름과 선택 지원자 수를 보이고, 0명이면 수를 숨기며 지금 탭을 표시한다', () => {
    mockServer()
    renderBar([tab('t1', '탭 1'), tab('t2', '금융 경험', 3)], { current: 't2' })

    expect(screen.getByRole('tab', { name: '탭 1' })).toHaveAttribute('aria-selected', 'false')
    const current = screen.getByRole('tab', { name: '금융 경험 (선택 지원자 3명)' })
    expect(current).toHaveAttribute('aria-selected', 'true')
  })

  it('탭을 누르면 그 탭으로 옮긴다', () => {
    mockServer()
    const onSelect = renderBar([tab('t1', '탭 1'), tab('t2', '금융 경험')])

    fireEvent.click(screen.getByRole('tab', { name: '금융 경험' }))

    expect(onSelect).toHaveBeenCalledWith('t2')
  })

  it('[+]로 빈 탭을 만들고 그 탭으로 옮긴다', async () => {
    const fetch = mockServer()
    const onSelect = renderBar([tab('t1', '탭 1')])

    fireEvent.click(screen.getByRole('button', { name: '새 탭' }))

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('t9'))
    expect(sent(fetch, 'POST').map((request) => new URL(request.url).pathname)).toContain(
      '/api/stages/s1/tabs',
    )
  })

  it('탭이 20개면 [+]를 끈다', () => {
    mockServer()
    renderBar(Array.from({ length: 20 }, (_, index) => tab(`t${index + 1}`, `탭 ${index + 1}`)))

    expect(screen.getByRole('button', { name: '새 탭' })).toBeDisabled()
  })

  it('마지막 탭에는 지우기가 없고, 지우기는 확인한 뒤에 지우며 지금 탭이면 옆 탭으로 옮긴다', async () => {
    const fetch = mockServer()
    const onSelect = renderBar([tab('t1', '탭 1'), tab('t2', '금융 경험')], { current: 't2' })

    fireEvent.click(screen.getByRole('button', { name: '금융 경험 지우기' }))
    const dialog = await screen.findByRole('alertdialog')
    expect(dialog).toHaveTextContent('이 탭의 선택 지원자와 대화가 모두 지워져요')
    expect(sent(fetch, 'DELETE')).toHaveLength(0)
    fireEvent.click(within(dialog).getByRole('button', { name: '지우기' }))

    await waitFor(() => expect(sent(fetch, 'DELETE')).toHaveLength(1))
    expect(new URL(sent(fetch, 'DELETE')[0].url).pathname).toBe('/api/stages/s1/tabs/t2')
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith('t1'))
  })

  it('남은 탭이 하나면 지우기가 없다', () => {
    mockServer()
    renderBar([tab('t1', '탭 1')])

    expect(screen.queryByRole('button', { name: '탭 1 지우기' })).not.toBeInTheDocument()
  })

  it('이름을 두 번 누르면 바꿔 쓰고 Enter로 저장한다', async () => {
    const fetch = mockServer()
    renderBar([tab('t1', '탭 1'), tab('t2', '탭 2')])

    fireEvent.doubleClick(screen.getByRole('tab', { name: '탭 2' }))
    const input = screen.getByRole('textbox', { name: '탭 이름' })
    fireEvent.change(input, { target: { value: '  금융 경험  ' } })
    fireEvent.keyDown(input, { key: 'Enter' })

    await waitFor(() => expect(sent(fetch, 'PATCH')).toHaveLength(1))
    const request = sent(fetch, 'PATCH')[0]
    expect(new URL(request.url).pathname).toBe('/api/stages/s1/tabs/t2')
    expect(await request.json()).toEqual({ name: '금융 경험' })
  })

  it('끝난 전형에서는 탭을 만들거나 지울 수 없다', () => {
    mockServer()
    renderBar([tab('t1', '탭 1'), tab('t2', '탭 2')], { editable: false })

    expect(screen.queryByRole('button', { name: '새 탭' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '탭 2 지우기' })).not.toBeInTheDocument()
  })
})
