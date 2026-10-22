import { describe, expect, it, vi } from 'vitest'

import { readChat } from '@/features/chat/api'
import { ApiError } from '@/lib/api/client'
import { streamOf } from '@/test/stream'

const ANSWER = {
  intent: 'ANSWER',
  mode: null,
  message: '비교했어요.',
  items: [],
  sources: [],
  agents: [],
  selectionChanged: false,
  stub: false,
}

describe('readChat', () => {
  it('진행 알림을 차례로 넘기고 done의 답을 돌려준다', async () => {
    const onStatus = vi.fn()
    const onItem = vi.fn()
    const item = { applicationId: 'a1', label: 'RDBMS', text: 'Oracle 원장 설계', status: 'OK' }

    const answer = await readChat(
      streamOf(
        'event:status\ndata:{"text":"2명 자료를 정리하고 있어요"}\n\n',
        `event:item\ndata:${JSON.stringify(item)}\n\n`,
        `event:done\ndata:${JSON.stringify(ANSWER)}\n\n`,
      ),
      { onStatus, onItem },
    )

    expect(onStatus).toHaveBeenCalledWith('2명 자료를 정리하고 있어요')
    expect(onItem).toHaveBeenCalledWith(item)
    expect(answer).toEqual(ANSWER)
  })

  it('error 이벤트는 상태와 code를 담은 ApiError로 던진다', async () => {
    const reading = readChat(
      streamOf('event:error\ndata:{"status":502,"code":"AI_UNAVAILABLE"}\n\n'),
      { onStatus: vi.fn(), onItem: vi.fn() },
    )

    await expect(reading).rejects.toEqual(new ApiError(502, 'AI_UNAVAILABLE', ''))
    await expect(reading).rejects.toBeInstanceOf(ApiError)
  })

  it('done 없이 끝나면 AI_UNAVAILABLE로 던진다', async () => {
    const reading = readChat(streamOf('event:status\ndata:{"text":"a"}\n\n'), {
      onStatus: vi.fn(),
      onItem: vi.fn(),
    })

    await expect(reading).rejects.toMatchObject({ status: 502, code: 'AI_UNAVAILABLE' })
  })
})
