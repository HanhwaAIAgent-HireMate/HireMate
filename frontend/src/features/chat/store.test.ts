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

/** 멘션과 처리 단계, 질문한 담당자가 없는 지난 턴 (이 기능 전의 기록과 같다) */
function turn(message: string): ChatTurn {
  return { message, mentions: [], answer, steps: [], seconds: null, asker: null }
}

describe('turnsToMessages', () => {
  it('같은 탭을 함께 쓰는 담당자 가운데 누가 물었는지 질문에 남긴다', () => {
    const asked = { ...turn('경력 알려줘'), asker: { memberId: 'm2', name: '김담당' } }

    expect(turnsToMessages([asked])[0]).toMatchObject({ role: 'user', asker: '김담당' })
  })

  it('서버에 남은 지난 턴을 담당자 질문과 AI 답 순서로 펼친다', () => {
    const messages = turnsToMessages([
      turn('금융 경험 찾아줘'),
      {
        ...turn('그중 두 번째 사람 강점은?'),
        answer: { ...answer, intent: 'ANSWER', mode: null },
      },
    ])

    expect(messages.map((message) => message.role)).toEqual(['user', 'ai', 'user', 'ai'])
    expect(messages[0]).toEqual({
      role: 'user',
      text: '금융 경험 찾아줘',
      mentions: [],
      asker: null,
    })
    expect(messages[1]).toEqual({ role: 'ai', answer, steps: [], seconds: null })
  })

  it('질문에 쓴 @멘션과 답의 처리 단계, 걸린 시간을 살린다', () => {
    const mention = { applicationId: 'a1', name: '정유민' }
    const steps = ['요청을 확인하고 있어요', '지원자 자료를 확인하고 있어요']

    const [question, reply] = turnsToMessages([
      { ...turn('경력 알려줘'), mentions: [mention], steps, seconds: 7 },
    ])

    expect(question).toEqual({
      role: 'user',
      text: '경력 알려줘',
      mentions: [mention],
      asker: null,
    })
    expect(reply).toEqual({ role: 'ai', answer, steps, seconds: 7 })
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
    append('t1', { role: 'user', text: '예전 질문', mentions: [], asker: null })

    load('t1', turnsToMessages([turn('금융 경험 찾아줘')]))

    expect(useChatStore.getState().threads.t1).toEqual([
      { role: 'user', text: '금융 경험 찾아줘', mentions: [], asker: null },
      { role: 'ai', answer, steps: [], seconds: null },
    ])
  })

  it('대화를 브라우저에 따로 남기지 않는다', () => {
    useChatStore.getState().append('t1', { role: 'user', text: '질문', mentions: [], asker: null })

    expect(sessionStorage.length).toBe(0)
  })
})
