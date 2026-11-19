import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import ts from 'typescript'

// 直接编译现有 API 模块，不额外引入前端测试依赖。
const source = readFileSync(new URL('../src/api/rag.ts', import.meta.url), 'utf8')
  .replace('import.meta.env.VITE_API_BASE', 'undefined')
const code = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText
const { streamChat, ApiError } = await import(`data:text/javascript,${encodeURIComponent(code)}`)

function response(parts) {
  const bytes = parts.map((part) => typeof part === 'string' ? new TextEncoder().encode(part) : part)
  return new Response(new ReadableStream({
    start(controller) {
      bytes.forEach((part) => controller.enqueue(part))
      controller.close()
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } })
}

test('decodes split UTF-8, ignores unknown events, and accepts done', async () => {
  const originalFetch = globalThis.fetch
  const encoded = new TextEncoder().encode('data: {"type":"delta","content":"法规"}\n\n')
  const split = encoded.indexOf(0xe8) + 1
  globalThis.fetch = async () => response([
    'data: {"type":"future","x":1}\n\n', encoded.slice(0, split), encoded.slice(split),
    'data: {"type":"done","session_id":"s","answer":"法规","sources":[]}\n\n',
  ])
  const events = []
  try {
    await streamChat({ question: '问题' }, (event) => events.push(event))
    assert.deepEqual(events.map((item) => item.type), ['delta', 'done'])
    assert.equal(events[0].content, '法规')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('server error event rejects with its message', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => response(['data: {"type":"error","message":"问答失败"}\n\n'])
  try {
    await assert.rejects(streamChat({ question: '问题' }, () => {}),
      (error) => error instanceof ApiError && error.message === '问答失败')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('stream without done or error rejects as interrupted', async () => {
  const originalFetch = globalThis.fetch
  globalThis.fetch = async () => response(['data: {"type":"delta","content":"半句"}\n\n'])
  try {
    await assert.rejects(streamChat({ question: '问题' }, () => {}),
      (error) => error instanceof ApiError && error.message.includes('连接中断'))
  } finally {
    globalThis.fetch = originalFetch
  }
})
