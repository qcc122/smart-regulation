<script setup lang="ts">
import { ref } from 'vue'
import type { TraceStep } from '../types/rag'

defineProps<{
  steps: TraceStep[]
  isLoading: boolean
}>()

const expanded = ref<Record<string, boolean>>({})

const statusText: Record<TraceStep['status'], string> = {
  pending: '等待',
  running: '执行中',
  success: '完成',
  error: '失败',
}

function toggle(id: string): void {
  expanded.value[id] = !expanded.value[id]
}
</script>

<template>
  <section class="panel">
    <header class="panel__header">
      <div>
        <h2>Agent 执行过程</h2>
        <p>任务分解、工具调用与执行状态</p>
      </div>
      <span class="panel__count">{{ steps.filter((s) => s.status === 'success').length }}/{{ steps.length }}</span>
    </header>

    <div class="panel__body">
      <div v-if="steps.length === 0" class="panel__empty">提问后展示本轮任务的完整执行轨迹</div>
      <ol v-else class="trace">
        <li v-for="step in steps" :key="step.id" class="trace__item" :class="`trace__item--${step.status}`">
          <span class="trace__node">
            <span v-if="step.status === 'success'" class="trace__check">✓</span>
            <span v-else-if="step.status === 'error'" class="trace__cross">!</span>
            <span v-else-if="step.status === 'running'" class="trace__spin" />
            <span v-else class="trace__dot" />
          </span>
          <div class="trace__content">
            <div class="trace__head">
              <strong>{{ step.title }}</strong>
              <span class="trace__status">{{ statusText[step.status] }}</span>
              <span v-if="step.durationMs !== undefined" class="trace__time">{{ step.durationMs }} ms</span>
            </div>
            <p class="trace__detail">{{ step.detail }}</p>
            <template v-if="step.payload">
              <button class="trace__toggle" type="button" @click="toggle(step.id)">
                {{ expanded[step.id] ? '隐藏调用参数' : '查看调用参数' }}
              </button>
              <pre v-if="expanded[step.id]" class="trace__payload">{{ step.payload }}</pre>
            </template>
          </div>
        </li>
      </ol>
      <p v-if="isLoading" class="trace__foot">任务执行中，状态实时更新…</p>
    </div>
  </section>
</template>