import type {
  ApiEnvelope,
  ChatRequest,
  ChatResponse,
  DocumentItem,
  SessionHistory,
  SessionSummary,
  StreamEvent,
  UploadResult,
} from '../types/rag'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init: RequestInit = {}, timeoutMs = 15000): Promise<T> {
  const timeoutCtrl = new AbortController()
  const timer = setTimeout(() => timeoutCtrl.abort(), timeoutMs)
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, signal: init.signal ?? timeoutCtrl.signal })
  } catch (error) {
    if (init.signal?.aborted) throw error
    if (timeoutCtrl.signal.aborted) throw new ApiError('请求超时，请稍后刷新检查处理结果', 408)
    throw new ApiError('网络异常或服务不可用，请稍后重试', 0)
  } finally {
    clearTimeout(timer)
  }

  const payload = (await response.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!payload || payload.code !== 0 || !response.ok) {
    const fallback = response.status >= 500 ? '服务器开小差了，请稍后重试' : `请求失败（HTTP ${response.status}）`
    throw new ApiError(payload?.message || fallback, response.status)
  }
  return payload.data
}

/** 解析 SSE 帧；TextDecoder 增量解码保证中文等多字节字符不会在分片边界被截断 */
export async function streamChat(
  payload: ChatRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (error) {
    if (signal?.aborted) return
    throw new ApiError('无法连接后端流式接口', 0)
  }

  if (!response.ok || !response.body) {
    throw new ApiError(`流式请求失败（HTTP ${response.status}）`, response.status)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  let terminal = false
  const consume = (raw: string): void => {
    const line = raw.split('\n').find((item) => item.startsWith('data:'))
    if (!line) return
    const text = line.slice(5).trim()
    if (!text || text === '[DONE]') return
    let event: StreamEvent
    try {
      event = JSON.parse(text) as StreamEvent
    } catch {
      throw new ApiError('流式响应格式错误', 0)
    }
    if (!event || !['node', 'tool', 'sources', 'delta', 'done', 'error'].includes(event.type)) return
    onEvent(event)
    if (event.type === 'done' || event.type === 'error') terminal = true
    if (event.type === 'error') throw new ApiError(event.message, 0)
  }

  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer = (buffer + decoder.decode(value, { stream: true })).replaceAll('\r\n', '\n')
      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''
      frames.forEach(consume)
    }
    buffer += decoder.decode()
    if (buffer.trim()) consume(buffer)
    if (!signal?.aborted && !terminal) throw new ApiError('连接中断，回答未完成', 0)
  } finally {
    if (!terminal) await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}

export const ragApi = {
  checkHealth: (): Promise<{ status: string }> => request<{ status: string }>('/health', {}, 8000),
  listDocuments: (): Promise<DocumentItem[]> => request<DocumentItem[]>('/documents'),
  uploadDocument: (file: File): Promise<UploadResult> => {
    const body = new FormData()
    body.append('file', file)
    return request<UploadResult>('/documents/upload', { method: 'POST', body }, 600000)
  },
  deleteDocument: (docId: string): Promise<null> =>
    request<null>(`/documents/${encodeURIComponent(docId)}`, { method: 'DELETE' }),
  chat: (payload: ChatRequest): Promise<ChatResponse> =>
    request<ChatResponse>(
      '/chat',
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
      60000,
    ),
  listSessions: (): Promise<SessionSummary[]> => request<SessionSummary[]>('/sessions'),
  createSession: (): Promise<SessionSummary> => request<SessionSummary>('/sessions', { method: 'POST' }),
  getSession: (id: string): Promise<SessionHistory> =>
    request<SessionHistory>(`/sessions/${encodeURIComponent(id)}`),
  deleteSession: (id: string): Promise<null> =>
    request<null>(`/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),
}
