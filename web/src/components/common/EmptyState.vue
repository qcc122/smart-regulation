<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <div class="empty-state">
    <div class="empty-state__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" width="20" height="20"><path d="M12 8v4M12 16h.01" /><circle cx="12" cy="12" r="9" /></svg>
    </div>
    <p class="empty-state__title">{{ title }}</p>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <div class="empty-state__action"><slot /></div>
  </div>
</template>