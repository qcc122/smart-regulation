export interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

export interface ChatRequest {
  question: string
  session_id?: string
  top_k?: number
}

export interface SourceItem {
  doc_id: string
  content: string
}

export interface ChatResponse {
  session_id: string
  answer: string
  sources: SourceItem[]
}

export type StreamEvent =
  | { type: 'sources'; sources: SourceItem[] }
  | { type: 'delta'; content: string }
  | { type: 'done'; session_id: string; answer: string; sources: SourceItem[] }
  | { type: 'error'; message: string }

export interface DocumentItem {
  doc_id: string
  chunk_count: number
}

export interface UploadResult {
  doc_id: string
  filename: string
  chunk_count: number
}

export type TraceStatus = 'pending' | 'running' | 'success' | 'error'

export type TraceKind = 'decision' | 'tool' | 'retrieval' | 'context' | 'generation'

export interface TraceStep {
  id: string
  title: string
  kind: TraceKind
  status: TraceStatus
  detail: string
  durationMs?: number
  payload?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: number
  sources?: SourceItem[]
  trace?: TraceStep[]
  isError?: boolean
  isDemo?: boolean
  isStreaming?: boolean
}

export interface SessionItem {
  id: string
  title: string
  createdAt: number
  updatedAt: number
  messages: ChatMessage[]
}