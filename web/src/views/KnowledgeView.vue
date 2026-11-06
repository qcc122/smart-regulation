<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAppState } from '../composables/use-app-state'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'
import EmptyState from '../components/common/EmptyState.vue'

const app = useAppState()
const { documents, documentsLoading, isUploading, isDemo } = app

const fileInput = ref<HTMLInputElement | null>(null)
const dragOver = ref(false)
const confirmDocId = ref('')

const totalChunks = computed(() => documents.value.reduce((sum, item) => sum + item.chunk_count, 0))

function pickFile(): void {
  fileInput.value?.click()
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) void app.handleUpload(file)
  input.value = ''
}

function onDrop(event: DragEvent): void {
  dragOver.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void app.handleUpload(file)
}

function confirmRemove(): void {
  const docId = confirmDocId.value
  confirmDocId.value = ''
  if (docId) void app.handleRemoveDocument(docId)
}
</script>

<template>
  <div class="kb-page">
    <header class="kb-page__header">
      <div>
        <h1>知识库管理</h1>
        <p>上传法规文档，构建向量检索知识库</p>
      </div>
      <button class="btn btn--ghost" type="button" :disabled="documentsLoading" @click="app.refreshDocuments()">
        {{ documentsLoading ? '刷新中…' : '刷新列表' }}
      </button>
    </header>

    <div v-if="isDemo" class="panel__notice">当前为演示模式，展示样例数据，上传与删除不会请求后端</div>

    <div class="kb-stats">
      <div class="kb-stat">
        <span class="kb-stat__value">{{ documents.length }}</span>
        <span class="kb-stat__label">文档总数</span>
      </div>
      <div class="kb-stat">
        <span class="kb-stat__value">{{ totalChunks }}</span>
        <span class="kb-stat__label">切分片段</span>
      </div>
      <div class="kb-stat">
        <span class="kb-stat__value">{{ isDemo ? '演示' : '真实' }}</span>
        <span class="kb-stat__label">当前模式</span>
      </div>
    </div>

    <div
      class="kb-upload"
      :class="{ 'kb-upload--over': dragOver, 'kb-upload--busy': isUploading }"
      role="button"
      tabindex="0"
      aria-label="上传文档"
      @click="pickFile"
      @keydown.enter="pickFile"
      @dragover.prevent="dragOver = true"
      @dragleave.prevent="dragOver = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".pdf,.docx" hidden @change="onFileChange" />
      <p class="kb-upload__title">{{ isUploading ? '正在解析并入库…' : '点击选择或拖拽文件到此处' }}</p>
      <p class="kb-upload__hint">支持 PDF / DOCX 格式，单个文件不超过 20MB</p>
    </div>

    <section class="kb-list">
      <div class="kb-list__head">
        <h2>文档列表</h2>
        <span>{{ documents.length }} 个文档</span>
      </div>
      <div class="kb-list__body">
        <div v-if="documentsLoading" class="kb-skeletons">
          <div v-for="i in 3" :key="i" class="skeleton" />
        </div>
        <EmptyState
          v-else-if="documents.length === 0"
          title="暂无文档"
          description="上传第一份法规文档后，即可在智能问答中参与检索"
        />
        <ul v-else class="kb-items">
          <li v-for="doc in documents" :key="doc.doc_id" class="kb-item">
            <span class="kb-item__icon">
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><path d="M14 2v6h6" /></svg>
            </span>
            <div class="kb-item__info">
              <span class="kb-item__id">{{ doc.doc_id }}</span>
              <span class="kb-item__meta">{{ doc.chunk_count }} 个片段</span>
            </div>
            <button class="icon-btn" type="button" :aria-label="`删除文档 ${doc.doc_id}`" @click="confirmDocId = doc.doc_id">×</button>
          </li>
        </ul>
      </div>
    </section>

    <ConfirmDialog
      :open="confirmDocId !== ''"
      title="删除文档"
      :message="`删除后文档片段不可恢复，确认删除 ${confirmDocId}？`"
      confirm-text="删除"
      danger
      @confirm="confirmRemove"
      @cancel="confirmDocId = ''"
    />
  </div>
</template>