import { fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'

import { StageEditor } from '@/features/posting/StageEditor'
import type { StageForm } from '@/features/posting/stages'

function Editor() {
  const [stages, setStages] = useState<StageForm[]>([
    { name: '서류 전형', type: 'DOCUMENT' },
    { name: '코딩테스트', type: 'ASSESSMENT' },
    { name: '1차 면접', type: 'INTERVIEW' },
  ])
  return <StageEditor stages={stages} onChange={setStages} problem={null} />
}

const order = () =>
  screen.getAllByRole('button', { name: /고치기$/ }).map((chip) => chip.textContent)

describe('전형 절차 편집', () => {
  it('끌 수 없어도 창의 버튼으로 옮기고, 초점이 따라가 이어서 옮긴다', async () => {
    render(<Editor />)
    expect(order()).toEqual(['코딩테스트 · 평가', '1차 면접 · 면접'])
    fireEvent.click(screen.getByRole('button', { name: '1차 면접 고치기' }))
    fireEvent.click(await screen.findByRole('button', { name: '1차 면접 앞으로' }))

    expect(order()).toEqual(['1차 면접 · 면접', '코딩테스트 · 평가'])
    // 서류 전형 앞으로는 갈 수 없어 앞으로 버튼이 꺼지고, 초점은 뒤로 버튼에 둔다
    expect(await screen.findByRole('button', { name: '1차 면접 앞으로' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '1차 면접 뒤로' })).toHaveFocus()
  })

  it('맨 앞의 서류 전형은 고치거나 뺄 수 없다', () => {
    render(<Editor />)
    expect(screen.getByTitle('서류 전형은 맨 앞에 고정돼요')).toHaveTextContent('서류 전형 · 서류')
    expect(screen.queryByRole('button', { name: '서류 전형 고치기' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '서류 전형 빼기' })).not.toBeInTheDocument()
  })

  it('[전형 추가]는 이름을 쓰고 [확인]을 눌러야 들어가고, [취소]하면 그대로다', async () => {
    render(<Editor />)
    fireEvent.click(screen.getByRole('button', { name: '전형 추가' }))
    fireEvent.change(await screen.findByRole('textbox', { name: '새 전형 이름' }), {
      target: { value: '2차 면접' },
    })
    expect(order()).toEqual(['코딩테스트 · 평가', '1차 면접 · 면접'])
    fireEvent.click(screen.getByRole('button', { name: '확인' }))
    expect(order()).toEqual(['코딩테스트 · 평가', '1차 면접 · 면접', '2차 면접 · 면접'])

    fireEvent.click(screen.getByRole('button', { name: '전형 추가' }))
    fireEvent.change(await screen.findByRole('textbox', { name: '새 전형 이름' }), {
      target: { value: '임원 면접' },
    })
    fireEvent.click(screen.getByRole('button', { name: '취소' }))
    expect(order()).toHaveLength(3)
  })

  it('이미 있는 이름은 [확인]을 누를 수 없다', async () => {
    render(<Editor />)
    fireEvent.click(screen.getByRole('button', { name: '전형 추가' }))
    fireEvent.change(await screen.findByRole('textbox', { name: '새 전형 이름' }), {
      target: { value: '1차 면접' },
    })
    expect(screen.getByText('이름이 같은 전형이 있어요.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '확인' })).toBeDisabled()
  })
})
