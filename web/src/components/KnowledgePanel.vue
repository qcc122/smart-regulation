<script setup lang="ts">
import { ref } from 'vue'
import type { DocumentItem } from '../types/rag'

defineProps<{
  documents: DocumentItem[]
  uploading: boolean
}>()

const emit = defineEmits<{
  (e: 'upload', file: File): void
  (e: 'refresh'): void
  (e: 'remove', id: string): void
}>()

const fileInput = ref<HTMLInputElement | null>(null)

function handleChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('upload', file)
  input.value = ''
}
</script>

<template>
  <section class="knowledge">
    <header class="knowledge__header">
      <span>知识库</span>
      <button class="icon-btn" type="button" aria-label="刷新文档列表" @click="emit('refresh')">
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M20 11a8 8 0 10-2.3 5.7M20 5v6h-6" /></svg>
      </button>
    </header>

    <label class="knowledge__upload" :class="{ 'knowledge__upload--busy': uploading }">
      <input ref="fileInput" type="file" accept=".pdf,.docx" :disabled="uploading" @change="handleChange" />
      <span>{{ uploading ? '正在解析并入库…' : '上传 PDF / DOCX' }}</span>
    </label>

    <div v-if="documents.length === 0" class="knowledge__empty">暂无文档，上传后可参与检索</div>
    <ul v-else class="knowledge__list">
      <li v-for="doc in documents" :key="doc.doc_id">
        <span class="knowledge__dot" />
        <span class="knowledge__id">{{ doc.doc_id }}</span>
        <span class="knowledge__count">{{ doc.chunk_count }} 片</span>
        <button class="icon-btn" type="button" :aria-label="`删除文档 ${doc.doc_id}`" @click="emit('remove', doc.doc_id)">×</button>
      </li>
    </ul>
  </section>
</template>