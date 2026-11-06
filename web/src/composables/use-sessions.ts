import { computed, ref, watch } from 'vue'
import type { ChatMessage, SessionItem } from '../types/rag'

const STORAGE_KEY = 'smart-regulation.sessions.v1'

export function createId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function loadSessions(): SessionItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? (parsed as SessionItem[]) : []
  } catch {
    return []
  }
}

// 模块级单例：跨视图共享会话状态，切换路由不丢失
const sessions = ref<SessionItem[]>(loadSessions())
const activeId = ref<string>(sessions.value[0]?.id ?? '')

const activeSession = computed<SessionItem | null>(
  () => sessions.value.find((item) => item.id === activeId.value) ?? null,
)

watch(
  sessions,
  (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
    } catch {
      // 浏览器隐私模式下 localStorage 不可用，静默降级为内存会话
    }
  },
  { deep: true },
)

function createSession(): SessionItem {
  const now = Date.now()
  const session: SessionItem = {
    id: createId(),
    title: '新会话',
    createdAt: now,
    updatedAt: now,
    messages: [],
  }
  sessions.value.unshift(session)
  activeId.value = session.id
  return session
}

function ensureSession(): SessionItem {
  return activeSession.value ?? createSession()
}

function selectSession(id: string): void {
  activeId.value = id
}

function removeSession(id: string): void {
  sessions.value = sessions.value.filter((item) => item.id !== id)
  if (activeId.value === id) {
    activeId.value = sessions.value[0]?.id ?? ''
  }
}

function appendMessage(sessionId: string, message: ChatMessage): void {
  const session = sessions.value.find((item) => item.id === sessionId)
  if (!session) return
  session.messages.push(message)
  session.updatedAt = Date.now()
  if (message.role === 'user' && session.title === '新会话') {
    session.title = message.content.slice(0, 18) || '新会话'
  }
}

function updateMessage(sessionId: string, messageId: string, patch: Partial<ChatMessage>): void {
  const session = sessions.value.find((item) => item.id === sessionId)
  const message = session?.messages.find((item) => item.id === messageId)
  if (message) Object.assign(message, patch)
}

export function useSessions() {
  return {
    sessions,
    activeId,
    activeSession,
    createSession,
    ensureSession,
    selectSession,
    removeSession,
    appendMessage,
    updateMessage,
  }
}