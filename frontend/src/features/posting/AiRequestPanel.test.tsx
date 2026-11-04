import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { AiRequestPanel } from './AiRequestPanel'

const base = { messages: [], examples: [], onSend: () => {} }

describe('AI 수정 요청 패널', () => {
  beforeAll(() => {
    // jsdom에는 스크롤이 없다
    Element.prototype.scrollIntoView = vi.fn()
  })

  it('처리 단계를 받는 요청은 기다리는 동안 단계를 세로선과 점으로 보인다', () => {
    render(
      <AiRequestPanel
        {...base}
        pending
        steps={[
          { text: '요청을 확인하고 있어요', depth: 0 },
          { text: '수정안을 쓰고 있어요', depth: 0 },
        ]}
      />,
    )

    expect(screen.getAllByTestId('root-step').map((item) => item.textContent)).toEqual([
      '요청을 확인하고 있어요',
      '수정안을 쓰고 있어요',
    ])
    expect(screen.queryByText('수정안을 만들고 있어요…')).not.toBeInTheDocument()
  })

  it('단계가 아직 오지 않았으면 기다리는 문구를 첫 단계로 보인다', () => {
    render(<AiRequestPanel {...base} pending steps={[]} />)

    expect(screen.getByTestId('root-step')).toHaveTextContent('수정안을 만들고 있어요')
  })

  it('처리 단계를 받지 않는 요청(안내 초안)은 지금처럼 기다리는 문구만 보인다', () => {
    render(<AiRequestPanel {...base} pending />)

    expect(screen.getByText('수정안을 만들고 있어요…')).toBeInTheDocument()
    expect(screen.queryByTestId('root-step')).not.toBeInTheDocument()
  })

  it('답에는 AI Chat처럼 처리 과정 단계 수와 걸린 시간을 접어 두고 누르면 펼친다', () => {
    render(
      <AiRequestPanel
        {...base}
        pending={false}
        messages={[
          { role: 'user', text: '우대 사항 추천해 줘' },
          {
            role: 'ai',
            text: '우대 사항 수정안을 만들었어요.',
            steps: [
              { text: '요청을 확인하고 있어요', depth: 0 },
              { text: '수정안을 쓰고 있어요', depth: 0 },
            ],
            seconds: 12,
          },
        ]}
      />,
    )
    const toggle = screen.getByRole('button', { name: /처리 과정 2단계/ })

    expect(toggle).toHaveTextContent('12초')
    expect(screen.queryByTestId('root-step')).not.toBeInTheDocument()
    fireEvent.click(toggle)
    expect(screen.getAllByTestId('root-step')).toHaveLength(2)
  })

  it('단계 없이 온 답(안내 초안)에는 처리 과정을 보이지 않는다', () => {
    render(
      <AiRequestPanel
        {...base}
        pending={false}
        messages={[{ role: 'ai', text: '말투를 바꿨어요.' }]}
      />,
    )

    expect(screen.queryByRole('button', { name: /처리 과정/ })).not.toBeInTheDocument()
  })
})
