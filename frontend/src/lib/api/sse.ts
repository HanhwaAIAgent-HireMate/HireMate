export type SseEvent = { event: string; data: string }

/**
 * SSE 응답 본문을 이벤트로 읽는다. 이름 없는 이벤트와 주석(: ping)은 건너뛴다.
 * POST로 여는 스트림이라 EventSource 대신 fetch 본문을 직접 읽는다.
 */
export async function* readEvents(body: ReadableStream<Uint8Array>): AsyncGenerator<SseEvent> {
  const reader = body.getReader()
  // 한글은 여러 바이트라 조각 경계에서 갈라질 수 있다. stream으로 이어 푼다
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      // 끝의 \r은 다음 조각의 \n과 한 줄바꿈일 수 있어 남겨 둔다
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n|\r(?!$)/g, '\n')
      let end = buffer.indexOf('\n\n')
      while (end >= 0) {
        const event = parse(buffer.slice(0, end))
        buffer = buffer.slice(end + 2)
        if (event) yield event
        end = buffer.indexOf('\n\n')
      }
    }
  } finally {
    reader.releaseLock()
  }
}

function parse(block: string): SseEvent | null {
  let event = ''
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith(':')) continue
    const colon = line.indexOf(':')
    const field = colon < 0 ? line : line.slice(0, colon)
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '')
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return event ? { event, data: data.join('\n') } : null
}
