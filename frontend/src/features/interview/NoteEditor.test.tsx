import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { NoteEditor } from './NoteEditor'
import { ApiError } from '@/lib/api/client'

beforeEach(() => {
  localStorage.clear()
  save.mockReset()
  reload.mockClear()
})

const save = vi.fn<(text: string, version: number) => Promise<{ text: string; version: number }>>()
const reload = vi.fn().mockResolvedValue(undefined)
function editor(text = '서버 원본', version = 1, account = 'member') {
  const client = new QueryClient()
  client.setQueryData(['auth', 'me'], { companyId: 'company', memberId: account })
  return (
    <QueryClientProvider client={client}>
      <NoteEditor
        stageId="stage"
        applicationId="app"
        field="memo"
        label="내 메모"
        description="비공개"
        text={text}
        version={version}
        editable
        save={save}
        reload={reload}
      />
    </QueryClientProvider>
  )
}

it('저장 실패 후 이동·새로고침에 해당하는 재마운트에서 초안을 복구한다', async () => {
  save.mockRejectedValueOnce(new Error('offline'))
  const view = render(editor())
  fireEvent.change(screen.getByLabelText('내 메모', { selector: 'textarea' }), {
    target: { value: '실패한 초안' },
  })
  fireEvent.click(screen.getByRole('button', { name: '내 메모 저장' }))
  await screen.findByRole('alert')
  view.unmount()
  render(editor())
  expect(screen.getByRole('textbox')).toHaveValue('실패한 초안')
  expect(screen.getByText('저장되지 않은 초안을 복구했어요.')).toBeInTheDocument()
})

it('같은 브라우저의 다른 계정에는 초안을 표시하지 않는다', () => {
  const view = render(editor())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '나만 볼 내용' } })
  view.unmount()
  render(editor('다른 계정 원본', 1, 'other'))
  expect(screen.getByRole('textbox')).toHaveValue('다른 계정 원본')
})

it('서버 버전이 갱신돼도 작성 중인 내용을 유지하고 명시적 재저장에 최신 버전을 쓴다', async () => {
  save.mockResolvedValueOnce({ text: '내 초안', version: 3 })
  const view = render(editor())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '내 초안' } })
  view.rerender(editor('다른 창의 내용', 2))
  expect(screen.getByRole('textbox')).toHaveValue('내 초안')
  expect(screen.getByText('서버 내용: 다른 창의 내용')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '현재 초안으로 다시 저장' }))
  await waitFor(() => expect(save).toHaveBeenLastCalledWith('내 초안', 2))
  await waitFor(() => expect(localStorage.length).toBe(0))
})

it('409 저장 충돌 시 최신 내용을 조회하고 초안을 보관한다', async () => {
  save.mockRejectedValueOnce(new ApiError(409, 'MEMO_CONFLICT', ''))
  render(editor())
  fireEvent.change(screen.getByRole('textbox'), { target: { value: '보존할 초안' } })
  fireEvent.click(screen.getByRole('button', { name: '내 메모 저장' }))
  await screen.findByText('다른 화면에서 변경됐어요. 아래 최신 내용과 현재 초안을 비교해 주세요.')
  expect(screen.getByRole('textbox')).toHaveValue('보존할 초안')
  expect(reload).toHaveBeenCalled()
  expect(localStorage.length).toBe(1)
})
