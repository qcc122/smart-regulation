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
  citation_id?: string
  parent_id?: string
  title?: string
  source_file?: string
  page?: number | null
  section_path?: string[]
  chapter?: string | null
  article_no?: string | null
  retrieval_score?: number | null
}

export interface ChatResponse {
  session_id: string
  answer: string
  sources: SourceItem[]
}

export type StreamEvent =
  | { type: 'node' | 'tool'; id: string; name: string; status: 'running' | 'success' | 'error' }
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

export type TraceStatus = 'pending' | 'running' | 'success' | 'error' | 'cancelled'

export type TraceKind = 'decision' | 'tool' | 'retrieval' | 'context' | 'generation' | 'control'

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

export type SessionSummary = Omit<SessionItem, 'messages'>

export interface SessionHistory extends SessionSummary {
  messages: Pick<ChatMessage, 'id' | 'role' | 'content' | 'sources'>[]
}
