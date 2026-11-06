<script setup lang="ts">
import { ref } from 'vue'
import type { SourceItem } from '../types/rag'

defineProps<{
  sources: SourceItem[]
  isLoading: boolean
  isDemo: boolean
}>()

const expanded = ref<Record<number, boolean>>({})

function toggle(index: number): void {
  expanded.value[index] = !expanded.value[index]
}
</script>

<template>
  <section class="panel">
    <header class="panel__header">
      <div>
        <h2>知识库检索结果</h2>
        <p>RAG 召回的引用来源与匹配内容</p>
      </div>
      <span class="panel__count">{{ sources.length }} 条</span>
    </header>

    <div class="panel__body">
      <div v-if="isLoading" class="panel__loading">正在检索知识库…</div>
      <div v-else-if="sources.length === 0" class="panel__empty">
        发起一次提问后，这里会展示命中的法规片段
      </div>
      <template v-else>
        <div v-if="isDemo" class="panel__notice">以下为演示数据</div>
        <article v-for="(source, index) in sources" :key="`${source.doc_id}-${index}`" class="source-card">
          <header class="source-card__head">
            <span class="source-card__rank">#{{ index + 1 }}</span>
            <span class="source-card__doc">{{ source.doc_id }}</span>
            <span class="tag">引用片段</span>
          </header>
          <p class="source-card__text" :class="{ 'source-card__text--clamp': !expanded[index] }">{{ source.content }}</p>
          <button class="source-card__toggle" type="button" @click="toggle(index)">
            {{ expanded[index] ? '收起' : '展开全文' }}
          </button>
        </article>
      </template>
    </div>
  </section>
</template>