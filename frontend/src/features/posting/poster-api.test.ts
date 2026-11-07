import { describe, expect, it, vi } from 'vitest'
import { readPosterProposal } from './poster-api'
import { streamOf } from '@/test/stream'
import type { ChatStep } from '@/features/chat/steps'

describe('포스터 처리 과정 스트림', () => {
  it('서버의 단계와 완료된 제안을 구분해서 받는다', async () => {
    const onStep = vi.fn<(step: ChatStep) => void>()
    const proposal = { reply: '준비했어요', recommendations: [], templates: [] }
    const answer = await readPosterProposal(
      streamOf(
        'event:status\ndata:{"text":"공고와 기업 정보를 확인하고 있어요","depth":0}\n\n',
        'event:status\ndata:{"text":"요청에 맞는 포스터 디자인을 구상하고 있어요","depth":0}\n\n',
        `event:done\ndata:${JSON.stringify(proposal)}\n\n`,
      ),
      onStep,
    )
    expect(onStep.mock.calls.map(([step]) => step.text)).toEqual([
      '공고와 기업 정보를 확인하고 있어요',
      '요청에 맞는 포스터 디자인을 구상하고 있어요',
    ])
    expect(answer).toEqual(proposal)
  })

  it('실패 또는 완료 이벤트 없는 종료를 성공 제안으로 취급하지 않는다', async () => {
    await expect(
      readPosterProposal(
        streamOf('event:error\ndata:{"status":502,"code":"AI_UNAVAILABLE"}\n\n'),
        vi.fn(),
      ),
    ).rejects.toMatchObject({ status: 502, code: 'AI_UNAVAILABLE' })
    await expect(readPosterProposal(streamOf(''), vi.fn())).rejects.toMatchObject({
      status: 502,
      code: 'AI_UNAVAILABLE',
    })
  })
})
