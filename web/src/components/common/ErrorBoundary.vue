<script setup lang="ts">
import { onErrorCaptured, ref } from 'vue'

const failed = ref(false)
const message = ref('')

onErrorCaptured((error) => {
  failed.value = true
  message.value = error instanceof Error ? error.message : String(error)
  console.error('[ErrorBoundary]', error)
  return false
})

function reload(): void {
  window.location.reload()
}
</script>

<template>
  <div class="eb-host">
    <slot v-if="!failed" />
    <div v-else class="error-boundary">
      <h2>页面出现异常</h2>
      <p>{{ message }}</p>
      <div class="error-boundary__actions">
        <button class="btn btn--ghost" type="button" @click="failed = false">重试</button>
        <button class="btn btn--primary" type="button" @click="reload">刷新页面</button>
      </div>
    </div>
  </div>
</template>