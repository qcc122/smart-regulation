import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

const source = readFileSync(new URL('../src/composables/use-agent-trace.ts', import.meta.url), 'utf8')
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const { recordTraceEvent, finishTrace } = await import(`data:text/javascript,${encodeURIComponent(code)}`)

test('same-name retries keep separate steps and duration comes from server event times', () => {
  const trace = []
  const starts = new Map()
  recordTraceEvent(trace, { type: 'node', id: 'i1', name: 'intent', status: 'running' }, starts, 100)
  recordTraceEvent(trace, { type: 'node', id: 'i1', name: 'intent', status: 'success' }, starts, 160)
  recordTraceEvent(trace, { type: 'tool', id: 't1', name: 'search_regulations', status: 'error' }, starts, 200)
  recordTraceEvent(trace, { type: 'tool', id: 't2', name: 'search_regulations', status: 'running' }, starts, 220)
  recordTraceEvent(trace, { type: 'tool', id: 't2', name: 'search_regulations', status: 'success' }, starts, 280)
  recordTraceEvent(trace, { type: 'sources', sources: [{}, {}] }, starts, 290)
  recordTraceEvent(trace, { type: 'done', session_id: 's', answer: '回答', sources: [] }, starts, 310)

  assert.deepEqual(trace.map((step) => step.status), [
    'success', 'error', 'success', 'success', 'success',
  ])
  assert.equal(trace[0].durationMs, 60)
  assert.equal(trace[1].durationMs, undefined)
  assert.equal(trace[2].durationMs, 60)
  assert.equal(trace[3].detail, '收到 2 条引用依据')
  assert.equal(trace[4].id, 'terminal')
})

test('cancelled and error terminal do not mark unfinished nodes successful', () => {
  const trace = []
  const starts = new Map()
  recordTraceEvent(trace, { type: 'node', id: 'a1', name: 'answer', status: 'running' }, starts, 100)
  finishTrace(trace, 'cancelled', '用户停止生成')
  assert.equal(trace[0].status, 'running')
  assert.equal(trace.at(-1).status, 'cancelled')
  finishTrace(trace, 'error', '连接中断')
  assert.equal(trace.filter((step) => step.id === 'terminal').length, 1)
  assert.equal(trace.at(-1).status, 'error')
})
