export interface SSEEvent {
  [key: string]: unknown
}

export async function* parseSSEStream(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent, void, unknown> {
  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      if (signal?.aborted) break
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.error) throw new Error(data.error)
            yield data
          } catch (e: unknown) {
            if (e instanceof Error && e.message !== 'Unknown' && !e.message.startsWith('data:')) {
              throw e
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock()
  }
}
