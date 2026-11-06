<script setup lang="ts">
import { computed } from 'vue'
import type { SessionItem } from '../types/rag'

const props = withDefaults(
  defineProps<{
    sessions: SessionItem[]
    activeId: string
    isOpen: boolean
    health: 'online' | 'offline' | 'checking'
    docCount: number
  }>(),
  { isOpen: true },
)

const emit = defineEmits<{
  (e: 'select', id: string): void
  (e: 'create'): void
  (e: 'remove', id: string): void
  (e: 'close'): void
}>()

const healthText = computed(() => {
  if (props.health === 'online') return 'API 已连接'
  if (props.health === 'checking') return '正在连接'
  return 'API 未连接'
})

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return `${date.getMonth() + 1}/${date.getDate()} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <aside class="sidebar" :class="{ 'sidebar--open': isOpen }">
    <header class="sidebar__brand">
      <div class="brand__mark">R</div>
      <div class="brand__text">
        <strong>住建法规助手</strong>
        <span>RAG + Agent 协同问答</span>
      </div>
      <button class="icon-btn sidebar__close" type="button" aria-label="关闭会话栏" @click="emit('close')">
        <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
      </button>
    </header>

    <button class="btn btn--primary sidebar__new" type="button" @click="emit('create')">
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
      新建会话
    </button>

    <nav class="sidebar__sessions" aria-label="历史会话">
      <p class="section-label">历史会话 · {{ sessions.length }}</p>
      <div v-if="sessions.length === 0" class="sidebar__empty">还没有会话，点击上方按钮开始提问</div>
      <button
        v-for="session in sessions"
        :key="session.id"
        class="session-item"
        :class="{ 'session-item--active': session.id === activeId }"
        type="button"
        @click="emit('select', session.id)"
      >
        <span class="session-item__title">{{ session.title }}</span>
        <span class="session-item__meta">{{ formatTime(session.updatedAt) }} · {{ session.messages.length }} 条消息</span>
        <span
          class="session-item__remove"
          role="button"
          tabindex="0"
          aria-label="删除会话"
          @click.stop="emit('remove', session.id)"
          @keydown.enter.stop="emit('remove', session.id)"
        >×</span>
      </button>
    </nav>

    <footer class="sidebar__footer">
      <div class="status-line">
        <span class="status-dot" :class="`status-dot--${health}`" />
        <span>{{ healthText }}</span>
      </div>
      <div class="status-line status-line--muted">
        <span>知识库文档</span><strong>{{ docCount }}</strong>
      </div>
    </footer>
  </aside>
</template>