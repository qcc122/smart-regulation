<script setup lang="ts">
import { useAppState } from '../../composables/use-app-state'

const { health, isDemo, streamingId, streamPaused, toggleDemo, pauseStream, resumeStream, stopStream } = useAppState()
</script>

<template>
  <header class="topbar">
    <RouterLink to="/" class="topbar__brand">
      <span class="topbar__logo">R</span>
      <div class="topbar__title">
        <strong>住建法规智能助手</strong>
        <small>RAG 检索 × Agent 编排</small>
      </div>
    </RouterLink>

    <nav class="topbar__nav" aria-label="主导航">
      <RouterLink class="topbar__link" to="/">智能问答</RouterLink>
      <RouterLink class="topbar__link" to="/knowledge">知识库</RouterLink>
    </nav>

    <div class="topbar__actions">
      <div v-if="streamingId" class="topbar__generating">
        <span class="spinner" />
        <span>生成中</span>
        <button class="btn btn--ghost btn--sm" type="button" @click="streamPaused ? resumeStream() : pauseStream()">
          {{ streamPaused ? '继续' : '暂停' }}
        </button>
        <button class="btn btn--ghost btn--sm" type="button" @click="stopStream">停止</button>
      </div>
      <span class="topbar__status">
        <span class="status-dot" :class="`status-dot--${health}`" />
        {{ health === 'online' ? '已连接' : health === 'checking' ? '连接中' : '离线' }}
      </span>
      <button class="btn btn--ghost" type="button" @click="toggleDemo">
        {{ isDemo ? '退出演示' : '演示模式' }}
      </button>
    </div>
  </header>
</template>