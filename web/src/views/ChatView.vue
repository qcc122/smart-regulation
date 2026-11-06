<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ApiError, streamChat } from '../api/rag'
import { createId, useSessions } from '../composables/use-sessions'
import { useAppState } from '../composables/use-app-state'
import { useTypewriter } from '../composables/use-typewriter'
import { TRACE_PHASES, cloneTrace, createTrace, updateStep } from '../composables/use-agent-trace'
import type { SourceItem, TraceStep } from '../types/rag'
import AgentTracePanel from '../components/AgentTracePanel.vue'
import ChatPanel from '../components/ChatPanel.vue'
import KnowledgePanel from '../components/KnowledgePanel.vue'
import RetrievalPanel from '../components/RetrievalPanel.vue'
import SessionSidebar from '../components/SessionSidebar.vue'
import ConfirmDialog from '../components/common/ConfirmDialog.vue'

type PanelKey = 'chat' | 'retrieval' | 'trace' | 'sessions'

const app = useAppState()
const { sessions, activeId, activeSession, createSession, selectSession, removeSession, ensureSession, appendMessage, updateMessage } = useSessions()
const { health, documents, isUploading, isDemo, topK, currentSources, currentTrace, streamingId, streamPaused } = app

const isLoading = ref(false)
const activePanel = ref<PanelKey>('chat')
const sidebarOpen = ref(false)
const confirmSessionId = ref('')
const confirmDocId = ref('')

const messages = computed(() => activeSession.value?.messages ?? [])

function phaseStatus(id: string): TraceStep['status'] {
  if (currentTrace.value.length === 0) return 'pending'
  const statuses = new Map(currentTrace.value.map((step) => [step.id, step.status]))
  if (id === 'retrieval' && statuses.get('retrieval') !== 'success') {
    return statuses.get('tool') ?? 'pending'
  }
  return statuses.get(id) ?? 'pending'
}

function handleCreateSession(): void {
  createSession()
  currentSources.value = []
  currentTrace.value = []
  activePanel.value = 'chat'
  sidebarOpen.value = false
}

// 将当前会话最后一条回答的引用与轨迹同步到右侧面板
function syncPanelsFromSession(): void {
  const lastAnswer = [...(activeSession.value?.messages ?? [])].reverse().find((item) => item.role === 'assistant')
  currentSources.value = lastAnswer?.sources ?? []
  currentTrace.value = lastAnswer?.trace ? cloneTrace(lastAnswer.trace) : []
}

function handleSelectSession(id: string): void {
  selectSession(id)
  syncPanelsFromSession()
  activePanel.value = 'chat'
  sidebarOpen.value = false
}

function requestRemoveSession(id: string): void {
  confirmSessionId.value = id
}

function requestRemoveDocument(docId: string): void {
  confirmDocId.value = docId
}

function confirmRemove(): void {
  const sessionId = confirmSessionId.value
  const docId = confirmDocId.value
  confirmSessionId.value = ''
  confirmDocId.value = ''
  if (sessionId) {
    removeSession(sessionId)
    syncPanelsFromSession()
  }
  if (docId) void app.handleRemoveDocument(docId)
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误'
}

function demoAnswer(question: string): { answer: string; sources: SourceItem[] } {
  return {
    answer:
      `【演示回答】针对「${question}」，本轮召回 3 个知识片段，并据此生成回答。\n\n` +
      '演示模式不调用后端接口，接入真实 API 后将返回基于知识库内容的生成结果，同时在右侧展示真实引用来源。',
    sources: [
      { doc_id: 'demo-doc-01', content: '示例片段一：此处为演示用占位文本，用于展示引用来源卡片的排版、编号与展开交互，不代表真实法规内容。' },
      { doc_id: 'demo-doc-02', content: '示例片段二：真实运行时，这里会显示 Milvus 向量检索命中的 chunk 内容，并在 Agent 轨迹中记录工具调用耗时与状态。' },
      { doc_id: 'demo-doc-03', content: '示例片段三：关闭演示模式后，页面会通过 /api/chat/stream 请求后端，答案与引用片段均由大模型与知识库生成。' },
    ],
  }
}
async function handleSend(question: string): Promise<void> {
  if (isLoading.value) return
  const session = ensureSession()
  activePanel.value = 'chat'
  appendMessage(session.id, { id: createId(), role: 'user', content: question, createdAt: Date.now() })

  const trace = createTrace(question, topK.value)
  currentTrace.value = trace
  currentSources.value = []
  isLoading.value = true
  const startedAt = performance.now()
  updateStep(trace, 'intent', { status: 'success', detail: `提取检索意图：${question.slice(0, 24)}`, durationMs: 0 })
  updateStep(trace, 'decision', { status: 'success', detail: '决策：调用 vector_search 检索知识库，再由 LLM 依据引用生成' })
  updateStep(trace, 'tool', { status: 'running' })

  const assistantId = createId()
  appendMessage(session.id, {
    id: assistantId,
    role: 'assistant',
    content: '',
    createdAt: Date.now(),
    sources: [],
    isStreaming: true,
    isDemo: isDemo.value,
  })
  streamingId.value = assistantId
  streamPaused.value = false

  const tw = useTypewriter({
    onUpdate: (text) => updateMessage(session.id, assistantId, { content: text }),
  })
  const controller = new AbortController()
  app.bindStream(tw, controller)

  let finalized = false
  function finalize(opts: { sources?: SourceItem[]; aborted?: boolean }): void {
    if (finalized) return
    finalized = true
    const elapsed = Math.round(performance.now() - startedAt)
    updateStep(trace, 'generation', {
      status: 'success',
      detail: opts.aborted ? '已停止生成' : '已基于参考资料生成回答',
      durationMs: elapsed,
    })
    updateMessage(session.id, assistantId, {
      isStreaming: false,
      sources: opts.sources ?? currentSources.value,
      trace: cloneTrace(trace),
    })
  }

  try {
    if (isDemo.value) {
      await delay(350)
      const demo = demoAnswer(question)
      currentSources.value = demo.sources
      updateStep(trace, 'tool', { status: 'success', detail: `调用完成，返回 ${demo.sources.length} 个片段` })
      updateStep(trace, 'retrieval', { status: 'success', detail: `向量检索命中 ${demo.sources.length} 个片段` })
      updateStep(trace, 'context', { status: 'success', detail: '已将片段拼接进生成 Prompt' })
      updateStep(trace, 'generation', { status: 'running' })
      const step = Math.max(1, Math.ceil(demo.answer.length / 40))
      for (let i = 0; i < demo.answer.length; i += step) {
        if (controller.signal.aborted) break
        tw.push(demo.answer.slice(i, i + step))
        await delay(28)
      }
      if (controller.signal.aborted) {
        tw.stop()
        finalize({ aborted: true })
      } else {
        tw.setFullAnswer(demo.answer)
        tw.markDone()
        finalize({ sources: demo.sources })
      }
    } else {
      await streamChat(
        { question, session_id: session.id, top_k: topK.value },
        (event) => {
          if (event.type === 'sources') {
            currentSources.value = event.sources
            const elapsed = Math.round(performance.now() - startedAt)
            updateStep(trace, 'tool', { status: 'success', detail: `调用完成，返回 ${event.sources.length} 个片段`, durationMs: elapsed })
            updateStep(trace, 'retrieval', { status: 'success', detail: `向量检索命中 ${event.sources.length} 个法规片段` })
            updateStep(trace, 'context', { status: 'success', detail: '已将片段拼接进生成 Prompt' })
            updateStep(trace, 'generation', { status: 'running' })
          } else if (event.type === 'delta') {
            tw.push(event.content)
          } else if (event.type === 'done') {
            tw.setFullAnswer(event.answer)
            tw.markDone()
            currentSources.value = event.sources
            finalize({ sources: event.sources })
          } else if (event.type === 'error') {
            throw new ApiError(event.message, 0)
          }
        },
        controller.signal,
      )
      if (controller.signal.aborted) {
        tw.stop()
        finalize({ aborted: true })
      }
    }
  } catch (error) {
    if (controller.signal.aborted) {
      tw.stop()
      finalize({ aborted: true })
    } else {
      const detail = error instanceof ApiError ? error.message : errorMessage(error)
      updateStep(trace, 'tool', { status: 'error', detail })
      updateStep(trace, 'retrieval', { status: 'error', detail: '检索未完成' })
      updateStep(trace, 'context', { status: 'error', detail: '上下文未构建' })
      updateStep(trace, 'generation', { status: 'error', detail: '未生成回答' })
      updateMessage(session.id, assistantId, {
        isStreaming: false,
        isError: true,
        content: `请求失败：${detail}。请检查后端服务或切换演示模式查看界面。`,
        trace: cloneTrace(trace),
      })
    }
  } finally {
    isLoading.value = false
    app.releaseStream()
  }
}

function selectPanel(panel: PanelKey): void {
  if (panel === 'sessions') {
    sidebarOpen.value = true
    return
  }
  activePanel.value = panel
}

onMounted(() => {
  if (messages.value.length > 0) syncPanelsFromSession()
})
</script>

<template>
  <div class="chat-page">
    <div class="flow flow--page" aria-label="RAG 与 Agent 协同流程">
      <template v-for="(phase, index) in TRACE_PHASES" :key="phase.id">
        <span v-if="index > 0" class="flow__arrow">›</span>
        <div class="flow__node" :class="`flow__node--${phaseStatus(phase.id)}`">
          <span class="flow__index">{{ index + 1 }}</span>
          <span>{{ phase.label }}</span>
        </div>
      </template>
    </div>

    <div class="layout">
      <div v-if="sidebarOpen" class="drawer-mask" @click="sidebarOpen = false" />
      <div class="layout__sidebar" :class="{ 'layout__sidebar--open': sidebarOpen }">
        <SessionSidebar
          :sessions="sessions"
          :active-id="activeId"
          :is-open="sidebarOpen"
          :health="health"
          :doc-count="documents.length"
          @select="handleSelectSession"
          @create="handleCreateSession"
          @remove="requestRemoveSession"
          @close="sidebarOpen = false"
        />
        <KnowledgePanel
          :documents="documents"
          :uploading="isUploading"
          @upload="app.handleUpload"
          @refresh="app.refreshDocuments"
          @remove="requestRemoveDocument"
        />
      </div>

      <main class="workspace">
        <div class="workspace__chat" :class="{ 'mobile-active': activePanel === 'chat' }">
          <ChatPanel
            :messages="messages"
            :is-loading="isLoading"
            :is-demo="isDemo"
            :top-k="topK"
            :streaming-message-id="streamingId"
            :is-streaming-paused="streamPaused"
            @send="handleSend"
            @update:top-k="topK = $event"
            @pause="app.pauseStream"
            @resume="app.resumeStream"
            @skip="app.skipStream"
            @stop="app.stopStream"
          />
        </div>
        <div class="workspace__rail">
          <div class="rail__slot" :class="{ 'mobile-active': activePanel === 'retrieval' }">
            <RetrievalPanel :sources="currentSources" :is-loading="isLoading" :is-demo="isDemo" />
          </div>
          <div class="rail__slot" :class="{ 'mobile-active': activePanel === 'trace' }">
            <AgentTracePanel :steps="currentTrace" :is-loading="isLoading" />
          </div>
        </div>
      </main>
    </div>

    <nav class="mobile-tabs" aria-label="面板切换">
      <button
        v-for="tab in [
          { key: 'chat', label: '对话' },
          { key: 'retrieval', label: '检索' },
          { key: 'trace', label: '轨迹' },
          { key: 'sessions', label: '会话' },
        ]"
        :key="tab.key"
        type="button"
        :class="{ 'mobile-tabs__item--active': activePanel === tab.key }"
        @click="selectPanel(tab.key as PanelKey)"
      >
        {{ tab.label }}
      </button>
    </nav>

    <ConfirmDialog
      :open="confirmSessionId !== ''"
      title="删除会话"
      message="删除后该会话的聊天记录无法恢复，确认删除？"
      confirm-text="删除"
      danger
      @confirm="confirmRemove"
      @cancel="confirmSessionId = ''"
    />
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