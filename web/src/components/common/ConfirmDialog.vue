<script setup lang="ts">
withDefaults(
  defineProps<{
    open: boolean
    title?: string
    message: string
    confirmText?: string
    danger?: boolean
  }>(),
  { title: '确认操作', confirmText: '确认', danger: false },
)

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="open" class="dialog-mask" @click.self="emit('cancel')">
        <div class="dialog" role="dialog" aria-modal="true" :aria-label="title">
          <h3>{{ title }}</h3>
          <p>{{ message }}</p>
          <div class="dialog__actions">
            <button class="btn btn--ghost" type="button" @click="emit('cancel')">取消</button>
            <button class="btn" :class="danger ? 'btn--danger' : 'btn--primary'" type="button" @click="emit('confirm')">
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>