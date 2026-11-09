import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { AiRequestPanel } from './AiRequestPanel'

const base = { messages: [], examples: [], pending: false, onSend: () => {} }

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

  it('공고 수정 답이 참고한 NCS는 답 아래 출처 카드로 보인다', () => {
    render(
      <AiRequestPanel
        {...base}
        pending={false}
        messages={[
          {
            role: 'ai',
            text: '주요 업무(1줄 추가) 수정안을 만들었어요.',
            ncsSources: [
              {
                field: 'duties',
                number: 2,
                line: '배치 프로그램을 구현합니다',
                dutyName: '응용SW엔지니어링',
                unitCode: '2001020211_23v6',
                unitName: '서버프로그램 구현',
                taskName: '배치 프로그램 구현하기',
                sentence: '배치 프로그램을 구현 한다',
              },
            ],
          },
          { role: 'ai', text: '근무지: 회사가 알려 준 값이 없어 지어내지 않았어요.' },
        ]}
      />,
    )

    expect(screen.getAllByTestId('ncs-source')).toHaveLength(1)
    expect(screen.getByText('주요 업무 2')).toBeInTheDocument()
    expect(screen.getByText('배치 프로그램을 구현 한다')).toBeInTheDocument()
  })

  it('줄을 골라 둔 채 예시 문구를 누르면 고르기를 풀고 예시 요청으로 보낸다', () => {
    const onSend = vi.fn()
    const onClear = vi.fn()
    render(
      <AiRequestPanel
        {...base}
        examples={['포트폴리오도 필수로 받아줘']}
        focus={{ label: '자격 요건 2번', onClear }}
        onSend={onSend}
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: '포트폴리오도 필수로 받아줘' }))

    expect(onClear).toHaveBeenCalled()
    expect(onSend).toHaveBeenCalledWith('포트폴리오도 필수로 받아줘', { example: true })
  })

  it('입력칸은 여러 줄이고, Enter는 보내고 Shift + Enter는 보내지 않는다', () => {
    const onSend = vi.fn()
    render(<AiRequestPanel {...base} onSend={onSend} />)
    const input = screen.getByRole('textbox', { name: '수정할 내용' })
    expect(input.tagName).toBe('TEXTAREA')

    fireEvent.change(input, { target: { value: '우대 사항을 더 구체적으로' } })
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true })
    expect(onSend).not.toHaveBeenCalled()

    fireEvent.keyDown(input, { key: 'Enter' })
    expect(onSend).toHaveBeenCalledWith('우대 사항을 더 구체적으로')
  })
})
