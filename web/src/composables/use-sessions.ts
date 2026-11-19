import { computed, ref, watch, type Ref } from 'vue'
import { ragApi } from '../api/rag'
import type { ChatMessage, SessionItem, SessionSummary } from '../types/rag'

const STORAGE_KEY = 'smart-regulation.demo-sessions.v1'

export function createId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function loadDemoSessions(): SessionItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) as SessionItem[] : []
  } catch {
    return []
  }
}

// 真实会话由服务端保存；演示会话使用单独的本地数据，避免混入真实列表。
const demoSessions = ref<SessionItem[]>(loadDemoSessions())
const serverSessions = ref<SessionItem[]>([])
const demoActiveId = ref(demoSessions.value[0]?.id ?? '')
const serverActiveId = ref('')

watch(demoSessions, (value) => {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(value))
  } catch {
    // 浏览器禁止本地存储时，演示会话只保留在当前页面。
  }
}, { deep: true })

export function useSessions(isDemo: Ref<boolean>) {
  const sessions = computed(() => isDemo.value ? demoSessions.value : serverSessions.value)
  const activeId = computed(() => isDemo.value ? demoActiveId.value : serverActiveId.value)
  const activeSession = computed(() => sessions.value.find((item) => item.id === activeId.value) ?? null)

  function mergeSummary(item: SessionSummary): SessionItem {
    const cached = serverSessions.value.find((session) => session.id === item.id)
    return { ...item, messages: cached?.messages ?? [] }
  }

  async function refreshSessions(): Promise<void> {
    if (isDemo.value) return
    const rows = await ragApi.listSessions()
    if (isDemo.value) return
    serverSessions.value = rows.map(mergeSummary)
    if (!serverSessions.value.some((item) => item.id === serverActiveId.value)) {
      serverActiveId.value = serverSessions.value[0]?.id ?? ''
    }
    if (activeSession.value && activeSession.value.messages.length === 0) {
      await selectSession(activeSession.value.id)
    }
  }

  async function createSession(): Promise<SessionItem> {
    if (isDemo.value) {
      const now = Date.now()
      const item: SessionItem = { id: createId(), title: '新会话', createdAt: now, updatedAt: now, messages: [] }
      demoSessions.value.unshift(item)
      demoActiveId.value = item.id
      return item
    }
    const item = await ragApi.createSession()
    const session = { ...item, messages: [] }
    serverSessions.value.unshift(session)
    serverActiveId.value = session.id
    return session
  }

  async function ensureSession(): Promise<SessionItem> {
    return activeSession.value ?? createSession()
  }

  async function selectSession(id: string): Promise<void> {
    if (isDemo.value) {
      demoActiveId.value = id
      return
    }
    const history = await ragApi.getSession(id)
    const item = serverSessions.value.find((session) => session.id === id)
    if (!item) return
    const cached = new Map(item.messages.map((message) => [message.id, message]))
    item.messages = history.messages.map((message, index) => {
      const previous = cached.get(message.id) ?? item.messages[index]
      const match = previous?.role === message.role && previous?.content === message.content ? previous : undefined
      return { ...match, ...message, createdAt: match?.createdAt ?? history.createdAt }
    })
    serverActiveId.value = id
  }

  async function removeSession(id: string): Promise<void> {
    if (isDemo.value) {
      demoSessions.value = demoSessions.value.filter((item) => item.id !== id)
      if (demoActiveId.value === id) demoActiveId.value = demoSessions.value[0]?.id ?? ''
      return
    }
    await ragApi.deleteSession(id)
    serverSessions.value = serverSessions.value.filter((item) => item.id !== id)
    if (serverActiveId.value === id) serverActiveId.value = serverSessions.value[0]?.id ?? ''
    if (serverActiveId.value) await selectSession(serverActiveId.value)
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
    const message = sessions.value.find((item) => item.id === sessionId)?.messages.find((item) => item.id === messageId)
    if (message) Object.assign(message, patch)
  }

  return {
    sessions, activeId, activeSession, refreshSessions, createSession, ensureSession,
    selectSession, removeSession, appendMessage, updateMessage,
  }
}
