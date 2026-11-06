import { ref } from 'vue'

export type TypewriterState = 'idle' | 'running' | 'paused' | 'done'

export interface TypewriterOptions {
  onUpdate: (displayed: string) => void
  onFinish?: (displayed: string) => void
  tickMs?: number
  minCharsPerTick?: number
  maxCharsPerTick?: number
}

const DEFAULT_TICK_MS = 24
const DEFAULT_MIN_CHARS = 1
const DEFAULT_MAX_CHARS = 8

/**
 * 逐字显示引擎。
 * - 以 Unicode 码点为单位入队，避免 emoji / 生僻字被拆成半个代理对
 * - 自适应节奏：积压越多每 tick 显示越多字符，慢流时保持单字打字感
 * - 终帧用完整答案覆盖显示内容，保证任何丢帧都不丢字符
 */
export function useTypewriter(options: TypewriterOptions) {
  const tickMs = options.tickMs ?? DEFAULT_TICK_MS
  const minChars = options.minCharsPerTick ?? DEFAULT_MIN_CHARS
  const maxChars = options.maxCharsPerTick ?? DEFAULT_MAX_CHARS

  const state = ref<TypewriterState>('idle')
  let pending: string[] = []
  let displayed = ''
  let authoritative = ''
  let upstreamDone = false
  let instant = false
  let finished = false
  let timer: ReturnType<typeof setInterval> | undefined

  function notify(): void {
    options.onUpdate(displayed)
  }

  function clearTimer(): void {
    if (timer) {
      clearInterval(timer)
      timer = undefined
    }
  }

  function finish(): void {
    if (finished) return
    finished = true
    clearTimer()
    // 终帧的完整内容是最终权威来源；中断时则补齐队列中已收到的字符
    displayed = authoritative || displayed + pending.join('')
    pending = []
    state.value = 'done'
    notify()
    options.onFinish?.(displayed)
  }

  function tick(): void {
    if (pending.length === 0) {
      if (upstreamDone) finish()
      return
    }
    const backlog = pending.length
    const count = Math.min(maxChars, Math.max(minChars, Math.ceil(backlog / 12)))
    displayed += pending.splice(0, count).join('')
    notify()
    if (upstreamDone && pending.length === 0) finish()
  }

  function startTimer(): void {
    if (timer || finished || instant || state.value === 'paused') return
    state.value = 'running'
    timer = setInterval(tick, tickMs)
  }

  function push(text: string): void {
    if (finished) return
    const points = Array.from(text)
    if (instant) {
      displayed += points.join('')
      notify()
      return
    }
    pending.push(...points)
    startTimer()
  }

  function setFullAnswer(answer: string): void {
    authoritative = answer
    // 若动画已跳过，立即用权威内容刷新，避免等待终帧
    if (instant) {
      displayed = answer
      notify()
    }
  }

  function markDone(): void {
    upstreamDone = true
    if (instant) {
      finish()
      return
    }
    if (pending.length === 0) finish()
    else startTimer()
  }

  function pause(): void {
    if (state.value !== 'running') return
    clearTimer()
    state.value = 'paused'
  }

  function resume(): void {
    if (state.value !== 'paused') return
    state.value = 'idle'
    startTimer()
  }

  function skip(): void {
    instant = true
    clearTimer()
    displayed += pending.join('')
    pending = []
    if (authoritative) displayed = authoritative
    state.value = 'done'
    notify()
  }

  function stop(): void {
    upstreamDone = true
    finish()
  }

  function dispose(): void {
    clearTimer()
  }

  return { state, push, setFullAnswer, markDone, pause, resume, skip, stop, dispose }
}