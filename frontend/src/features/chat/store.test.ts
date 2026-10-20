import { beforeEach, describe, expect, it } from 'vitest'

import type { ChatTurn } from '@/features/chat/api'
import { turnsToMessages, useChatStore } from '@/features/chat/store'

const answer: ChatTurn['answer'] = {
  intent: 'FIND',
  mode: 'REPLACE',
  message: '지원자 8명 중 조건에 맞는 **3명**을 선택했어요.',
  items: [],
  sources: [],
  agents: [],
  selectionChanged: false,
  stub: false,
}

describe('turnsToMessages', () => {
  it('서버에 남은 지난 턴을 담당자 질문과 AI 답 순서로 펼친다', () => {
    const messages = turnsToMessages([
      { message: '금융 경험 찾아줘', answer },
      {
        message: '그중 두 번째 사람 강점은?',
        answer: { ...answer, intent: 'ANSWER', mode: null },
      },
    ])

    expect(messages.map((message) => message.role)).toEqual(['user', 'ai', 'user', 'ai'])
    expect(messages[0]).toEqual({ role: 'user', text: '금융 경험 찾아줘', mentions: [] })
    expect(messages[1]).toEqual({ role: 'ai', answer })
  })

  it('기록이 없으면 빈 목록이다', () => {
    expect(turnsToMessages([])).toEqual([])
  })
})

describe('useChatStore', () => {
  beforeEach(() => {
    useChatStore.setState({ threads: {} })
    sessionStorage.clear()
  })

  it('서버 기록을 불러오면 화면에 남은 대화를 그 기록으로 바꾼다', () => {
    const { append, load } = useChatStore.getState()
    append('s1', { role: 'user', text: '예전 질문', mentions: [] })

    load('s1', turnsToMessages([{ message: '금융 경험 찾아줘', answer }]))

    expect(useChatStore.getState().threads.s1).toEqual([
      { role: 'user', text: '금융 경험 찾아줘', mentions: [] },
      { role: 'ai', answer },
    ])
  })

  it('대화를 브라우저에 따로 남기지 않는다', () => {
    useChatStore.getState().append('s1', { role: 'user', text: '질문', mentions: [] })

    expect(sessionStorage.length).toBe(0)
  })
})
