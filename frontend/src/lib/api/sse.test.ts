import { describe, expect, it } from 'vitest'

import { readEvents, type SseEvent } from '@/lib/api/sse'
import { streamOf } from '@/test/stream'

async function collect(body: ReadableStream<Uint8Array>): Promise<SseEvent[]> {
  const events: SseEvent[] = []
  for await (const event of readEvents(body)) events.push(event)
  return events
}

describe('readEvents', () => {
  it('이벤트 중간에서 잘린 조각을 이어 읽는다', async () => {
    const events = await collect(streamOf('event: sta', 'tus\ndata: {"text":', '"a"}\n', '\n'))

    expect(events).toEqual([{ event: 'status', data: '{"text":"a"}' }])
  })

  it('data가 여러 줄이면 줄바꿈으로 잇는다', async () => {
    const events = await collect(streamOf('event:item\ndata:{"a":\ndata:1}\n\n'))

    expect(events).toEqual([{ event: 'item', data: '{"a":\n1}' }])
  })

  it('CRLF가 조각 경계에서 갈라져도 줄바꿈 하나로 읽는다', async () => {
    const events = await collect(streamOf('event:status\r', '\ndata:{}\r\n\r', '\n'))

    expect(events).toEqual([{ event: 'status', data: '{}' }])
  })

  it('주석과 CRLF 줄바꿈을 처리하고 여러 이벤트를 순서대로 낸다', async () => {
    const events = await collect(
      streamOf(': ping\r\n\r\nevent:status\r\ndata:{}\r\n\r\nevent:done\r\ndata:{"b":2}\r\n\r\n'),
    )

    expect(events).toEqual([
      { event: 'status', data: '{}' },
      { event: 'done', data: '{"b":2}' },
    ])
  })
})
