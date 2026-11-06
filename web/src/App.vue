<script setup lang="ts">
import { onMounted } from 'vue'
import AppTopbar from './components/layout/AppTopbar.vue'
import ErrorBoundary from './components/common/ErrorBoundary.vue'
import { useAppState } from './composables/use-app-state'
import { useToast } from './composables/use-toast'

const { checkHealth, refreshDocuments } = useAppState()
const { toasts, dismiss } = useToast()

onMounted(() => {
  void checkHealth()
  void refreshDocuments()
})
</script>

<template>
  <div class="app">
    <AppTopbar />

    <ErrorBoundary>
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </ErrorBoundary>

    <div class="toaster" aria-live="polite">
      <div
        v-for="item in toasts"
        :key="item.id"
        class="toast"
        :class="`toast--${item.kind}`"
        role="status"
        @click="dismiss(item.id)"
      >
        {{ item.message }}
      </div>
    </div>
  </div>
</template>