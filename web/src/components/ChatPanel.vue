<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { ChatMessage } from '../types/rag'

const props = defineProps<{
  messages: ChatMessage[]
  isLoading: boolean
  isDemo: boolean
  topK: number
  streamingMessageId: string | null
  isStreamingPaused: boolean
}>()

const emit = defineEmits<{
  (e: 'send', question: string): void
  (e: 'update:topK', value: number): void
  (e: 'pause'): void
  (e: 'resume'): void
  (e: 'skip'): void
  (e: 'stop'): void
}>()

const draft = ref('')
const scroller = ref<HTMLElement | null>(null)
const suggestions = [
  '施工许可证需要哪些申请材料？',
  '工程竣工验收备案有什么要求？',
  '简述知识库中关于质量责任的规定',
]

watch(
  () => [
    props.messages.length,
    props.isLoading,
    props.messages[props.messages.length - 1]?.content.length ?? 0,
  ],
  async () => {
    await nextTick()
    if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
  },
)

function sendQuestion(text: string): void {
  const question = text.trim()
  if (!question || props.isLoading) return
  emit('send', question)
  draft.value = ''
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendQuestion(draft.value)
  }
}

function formatTime(timestamp: number): string {
  const date = new Date(timestamp)
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
}
</script>

<template>
  <section class="chat">
    <header class="chat__header">
      <div>
        <h1>智能问答</h1>
        <p>提问后由 Agent 编排检索工具，RAG 提供引用依据</p>
      </div>
      <label class="topk">
        召回片段
        <select :value="topK" @change="emit('update:topK', Number(($event.target as HTMLSelectElement).value))">
          <option :value="3">3</option>
          <option :value="5">5</option>
          <option :value="8">8</option>
        </select>
      </label>
    </header>

    <div ref="scroller" class="chat__scroll">
      <div v-if="messages.length === 0" class="chat__welcome">
        <div class="welcome__badge">RAG · Agent</div>
        <h2>有什么法规问题想了解？</h2>
        <p>系统会检索知识库并给出带引用依据的回答</p>
        <div class="welcome__suggestions">
          <button v-for="item in suggestions" :key="item" type="button" @click="sendQuestion(item)">{{ item }}</button>
        </div>
      </div>

      <article
        v-for="message in messages"
        :key="message.id"
        class="message"
        :class="[`message--${message.role}`, { 'message--error': message.isError }]"
      >
        <div class="message__avatar">{{ message.role === 'user' ? '我' : 'A' }}</div>
        <div class="message__body">
          <div class="message__meta">
            <span>{{ message.role === 'user' ? '我' : '助手' }}</span>
            <span>{{ formatTime(message.createdAt) }}</span>
            <span v-if="message.isDemo" class="tag tag--demo">演示数据</span>
            <span v-if="message.isStreaming" class="tag tag--stream">
              {{ isStreamingPaused ? '已暂停' : '正在生成' }}
            </span>
          </div>
          <!-- 纯文本渲染：代码块、多段落、缩进与换行原样保留，流式期间不做 Markdown 解析 -->
          <div
            class="message__content"
            :class="{ 'message__content--stream': message.isStreaming }"
          >{{ message.content }}<span v-if="message.isStreaming" class="stream-cursor" /></div>

          <div v-if="message.isStreaming" class="stream-controls">
            <button type="button" @click="isStreamingPaused ? emit('resume') : emit('pause')">
              {{ isStreamingPaused ? '继续' : '暂停' }}
            </button>
            <button type="button" @click="emit('skip')">跳过动画</button>
            <button type="button" class="stream-controls__danger" @click="emit('stop')">停止生成</button>
          </div>

          <div v-if="message.role === 'assistant' && message.sources?.length" class="message__refs">
            引用 {{ message.sources.length }} 个知识片段
          </div>
        </div>
      </article>

      <div v-if="isLoading && !streamingMessageId" class="message message--assistant">
        <div class="message__avatar">A</div>
        <div class="message__body">
          <div class="message__meta"><span>助手</span></div>
          <div class="typing"><span /><span /><span /></div>
        </div>
      </div>
    </div>

    <footer class="chat__composer">
      <div v-if="isDemo" class="composer__notice">当前为演示模式，展示样例数据，不会请求后端接口</div>
      <div v-if="streamingMessageId" class="composer__streaming">回答正在逐字生成，可使用消息下方按钮暂停、继续或跳过</div>
      <div class="composer__box">
        <textarea
          v-model="draft"
          rows="2"
          maxlength="500"
          placeholder="输入问题，Enter 发送，Shift + Enter 换行"
          :disabled="isLoading && !streamingMessageId"
          @keydown="handleKeydown"
        />
        <button class="btn btn--primary composer__send" type="button" :disabled="isLoading || !draft.trim()" @click="sendQuestion(draft)">
          发送
        </button>
      </div>
      <div class="composer__foot">
        <p class="composer__hint">回答基于知识库检索结果生成，请以原文为准</p>
        <span class="composer__count" :class="{ 'composer__count--over': draft.length >= 500 }">{{ draft.length }}/500</span>
      </div>
    </footer>
  </section>
</template>