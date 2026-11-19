import assert from 'node:assert/strict'
import test from 'node:test'
import { ref } from 'vue'
import { createServer } from 'vite'

test('real sessions use server CRUD while demo sessions stay local', async () => {
  const saved = new Map()
  globalThis.localStorage = {
    getItem: (key) => saved.get(key) ?? null,
    setItem: (key, value) => saved.set(key, value),
  }
  const vite = await createServer({
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, entries: [] },
  })
  try {
    const { ragApi } = await vite.ssrLoadModule('/src/api/rag.ts')
    const now = Date.now()
    const summary = { id: 'server-1', title: '真实会话', createdAt: now, updatedAt: now }
    let deleted = ''
    ragApi.listSessions = async () => [summary]
    ragApi.getSession = async () => ({ ...summary, messages: [
      { id: 'm1', role: 'user', content: '你好' },
      { id: 'm2', role: 'assistant', content: '回答' },
    ] })
    ragApi.createSession = async () => ({ ...summary, id: 'server-2' })
    ragApi.deleteSession = async (id) => { deleted = id }

    const { useSessions } = await vite.ssrLoadModule('/src/composables/use-sessions.ts')
    const demo = ref(false)
    const state = useSessions(demo)
    await state.refreshSessions()
    assert.equal(state.activeSession.value?.messages[1].content, '回答')
    state.activeSession.value.messages = [
      { id: 'local-user', role: 'user', content: '你好', createdAt: now },
      { id: 'local-answer', role: 'assistant', content: '回答', createdAt: now,
        trace: [{ id: 'terminal', title: '本轮结束', kind: 'generation', status: 'success', detail: '完成' }] },
    ]
    await state.selectSession('server-1')
    assert.equal(state.activeSession.value.messages[1].trace?.[0].id, 'terminal')
    await state.createSession()
    assert.equal(state.activeId.value, 'server-2')
    await state.removeSession('server-2')
    assert.equal(deleted, 'server-2')

    demo.value = true
    await state.createSession()
    assert.equal(state.sessions.value.length, 1)
    assert.notEqual(state.activeId.value, 'server-1')
    demo.value = false
    assert.equal(state.activeId.value, 'server-1')
  } finally {
    await vite.close()
    delete globalThis.localStorage
  }
})
