import { fireEvent, render, screen } from '@testing-library/react'
import { beforeAll, describe, expect, it, vi } from 'vitest'

import { AiRequestPanel, type AiMessage } from '@/features/posting/AiRequestPanel'

const answer: AiMessage = {
  role: 'ai',
  text: '자격 요건 수정안을 만들었어요. 바뀐 부분을 확인하고 적용해 주세요.',
  sources: [
    {
      code: '2001020211_23v6',
      subdivision: '응용SW엔지니어링',
      name: '서버프로그램 구현',
      level: 5,
      definition: '업무 프로세스와 설계에 따라 서버 프로그램을 구현하는 능력이다.',
    },
  ],
}

beforeAll(() => {
  // jsdom에는 화면 스크롤이 없다
  Element.prototype.scrollIntoView = vi.fn()
})

function renderPanel(messages: AiMessage[]) {
  render(
    <AiRequestPanel messages={messages} examples={[]} pending={false} onSend={() => undefined} />,
  )
}

describe('AiRequestPanel', () => {
  it('NCS 근거를 답 아래에 접어 두고, 누르면 능력단위 정의를 보여 준다', () => {
    renderPanel([answer])

    const card = screen.getByText('NCS 근거 1개')
    const definition = screen.getByText(answer.sources![0].definition)
    expect(definition).not.toBeVisible()

    fireEvent.click(card)

    expect(definition).toBeVisible()
    expect(screen.getByText('서버프로그램 구현')).toBeVisible()
  })

  it('근거가 없는 답에는 카드를 보여 주지 않는다', () => {
    renderPanel([{ role: 'ai', text: '어느 칸을 고칠까요?' }])

    expect(screen.queryByText(/NCS 근거/)).not.toBeInTheDocument()
  })
})
