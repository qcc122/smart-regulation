import { ref } from 'vue'

export type ToastKind = 'info' | 'success' | 'error'

export interface ToastItem {
  id: number
  message: string
  kind: ToastKind
}

// 模块级单例：全局唯一的通知队列
const toasts = ref<ToastItem[]>([])
const timers = new Map<number, ReturnType<typeof setTimeout>>()
let seq = 0

export function useToast() {
  function dismiss(id: number): void {
    const timer = timers.get(id)
    if (timer) {
      clearTimeout(timer)
      timers.delete(id)
    }
    toasts.value = toasts.value.filter((item) => item.id !== id)
  }

  function notify(message: string, kind: ToastKind = 'info', duration = 3600): void {
    const id = ++seq
    toasts.value.push({ id, message, kind })
    if (toasts.value.length > 3) toasts.value.shift()
    timers.set(id, setTimeout(() => dismiss(id), duration))
  }

  return { toasts, notify, dismiss }
}