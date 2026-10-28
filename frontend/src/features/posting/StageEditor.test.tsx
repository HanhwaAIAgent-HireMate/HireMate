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
    fireEvent.click(screen.getByRole('button', { name: '1차 면접 고치기' }))
    fireEvent.click(await screen.findByRole('button', { name: '1차 면접 앞으로' }))

    expect(order()).toEqual(['서류 전형 · 서류', '1차 면접 · 면접', '코딩테스트 · 평가'])
    const back = await screen.findByRole('button', { name: '1차 면접 앞으로' })
    expect(back).toHaveFocus()

    fireEvent.click(back)
    expect(order()).toEqual(['1차 면접 · 면접', '서류 전형 · 서류', '코딩테스트 · 평가'])
    // 맨 앞이라 더 갈 수 없으면 뒤로 버튼에 초점을 둔다
    expect(await screen.findByRole('button', { name: '1차 면접 앞으로' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '1차 면접 뒤로' })).toHaveFocus()
  })
})
