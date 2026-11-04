import { describe, expect, it, vi } from 'vitest'

import { readPostingAnswer } from '@/features/posting/api'
import { ApiError } from '@/lib/api/client'
import { streamOf } from '@/test/stream'

const ANSWER = {
  reply: '주요 업무 수정안을 만들었어요.',
  agent: 'Posting Agent',
  stub: false,
  posting: {},
}

describe('readPostingAnswer', () => {
  it('처리 단계를 차례로 넘기고 done의 답을 돌려준다', async () => {
    const onStep = vi.fn()

    const answer = await readPostingAnswer(
      streamOf(
        'event:status\ndata:{"text":"요청을 확인하고 있어요","depth":0}\n\n',
        'event:status\ndata:{"text":"수정안을 쓰고 있어요","depth":0}\n\n',
        `event:done\ndata:${JSON.stringify(ANSWER)}\n\n`,
      ),
      onStep,
    )

    expect(onStep).toHaveBeenCalledTimes(2)
    expect(onStep).toHaveBeenNthCalledWith(1, { text: '요청을 확인하고 있어요', depth: 0 })
    expect(onStep).toHaveBeenNthCalledWith(2, { text: '수정안을 쓰고 있어요', depth: 0 })
    expect(answer).toEqual(ANSWER)
  })

  it('error 이벤트는 그 상태와 코드의 ApiError다', async () => {
    const error = await readPostingAnswer(
      streamOf('event:error\ndata:{"status":404,"code":"RECRUITMENT_NOT_FOUND"}\n\n'),
      vi.fn(),
    ).catch((thrown: unknown) => thrown)

    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 404, code: 'RECRUITMENT_NOT_FOUND' })
  })

  it('done 없이 끝나면 AI를 쓸 수 없다는 오류다', async () => {
    const error = await readPostingAnswer(
      streamOf('event:status\ndata:{"text":"요청을 확인하고 있어요","depth":0}\n\n'),
      vi.fn(),
    ).catch((thrown: unknown) => thrown)

    expect(error).toMatchObject({ status: 502, code: 'AI_UNAVAILABLE' })
  })
})
