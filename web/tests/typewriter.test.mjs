import assert from 'node:assert/strict'
import test from 'node:test'
import { createServer } from 'vite'

test('disposing immediately after SSE done preserves the final answer', async () => {
  const vite = await createServer({
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, entries: [] },
  })
  try {
    const { useTypewriter } = await vite.ssrLoadModule('/src/composables/use-typewriter.ts')
    let displayed = ''
    let finished = 0
    const tw = useTypewriter({
      onUpdate: (text) => { displayed = text },
      onFinish: () => { finished++ },
    })
    tw.push('暂未找到')
    tw.setFullAnswer('暂未找到可核验的法规依据。')
    tw.markDone()
    tw.dispose()
    assert.equal(displayed, '暂未找到可核验的法规依据。')
    assert.equal(finished, 1)
    assert.equal(tw.state.value, 'done')

    let completed = false
    const animated = useTypewriter({
      tickMs: 1, minCharsPerTick: 1, maxCharsPerTick: 1,
      onUpdate: () => {}, onFinish: () => { completed = true },
    })
    animated.push('逐字显示')
    animated.setFullAnswer('逐字显示')
    animated.markDone()
    assert.equal(completed, false)
    animated.skip()
    assert.equal(completed, true)
    animated.dispose()
  } finally {
    await vite.close()
  }
})
