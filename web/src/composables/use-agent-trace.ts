import type { StreamEvent, TraceStep, TraceStatus } from '../types/rag'

export const TRACE_PHASES = [
  { id: 'intent', label: '意图识别' },
  { id: 'decision', label: 'Agent 决策' },
  { id: 'retrieval', label: 'RAG 检索' },
  { id: 'context', label: '上下文构建' },
  { id: 'generation', label: '答案生成' },
] as const

export function createTrace(question: string, topK: number): TraceStep[] {
  return [
    {
      id: 'intent',
      title: '意图识别',
      kind: 'decision',
      status: 'pending',
      detail: '解析用户输入，提取检索意图',
    },
    {
      id: 'decision',
      title: 'Agent 决策',
      kind: 'decision',
      status: 'pending',
      detail: '编排策略：调用知识库检索工具获取法规依据',
    },
    {
      id: 'tool',
      title: '工具调用 · vector_search',
      kind: 'tool',
      status: 'pending',
      detail: '向后端 /api/chat 发起检索与生成请求',
      payload: JSON.stringify({ tool: 'vector_search', query: question, top_k: topK }, null, 2),
    },
    {
      id: 'retrieval',
      title: 'RAG 片段召回',
      kind: 'retrieval',
      status: 'pending',
      detail: '等待 Milvus 向量检索结果',
    },
    {
      id: 'context',
      title: '上下文构建',
      kind: 'context',
      status: 'pending',
      detail: '将命中片段编号拼接进生成 Prompt',
    },
    {
      id: 'generation',
      title: 'LLM 生成回答',
      kind: 'generation',
      status: 'pending',
      detail: 'glm-4-flash 基于参考资料生成答案',
    },
  ]
}

export function updateStep(trace: TraceStep[], id: string, patch: Partial<TraceStep>): void {
  const step = trace.find((item) => item.id === id)
  if (step) Object.assign(step, patch)
}

export function cloneTrace(trace: TraceStep[]): TraceStep[] {
  return trace.map((step) => ({ ...step }))
}

const NODE_TITLES: Record<string, string> = {
  intent: '意图识别',
  rag: '法规问答分支',
  chat: '聊天分支',
  answer: '法规回答',
  reply: '聊天回答',
  validate: '答案校验',
}

export function finishTrace(trace: TraceStep[], status: 'success' | 'error' | 'cancelled', detail: string): void {
  const terminal = trace.find((step) => step.id === 'terminal')
  if (terminal) {
    Object.assign(terminal, { status, detail })
  } else {
    trace.push({ id: 'terminal', title: '本轮结束', kind: 'generation', status, detail })
  }
}

// 只记录服务端确实发出的步骤；用任务 ID 配对开始/结束，重试也会保留独立记录。
export function recordTraceEvent(
  trace: TraceStep[], event: StreamEvent, starts: Map<string, number>, now: number,
): void {
  if (event.type === 'node' || event.type === 'tool') {
    const id = `${event.type}:${event.id}`
    const title = event.type === 'tool' ? `工具调用 · ${event.name}` : NODE_TITLES[event.name] ?? event.name
    const kind = event.type === 'tool' ? 'tool'
      : ['intent', 'rag', 'chat'].includes(event.name) ? 'decision' : 'generation'
    const step = trace.find((item) => item.id === id)
    if (event.status === 'running') starts.set(id, now)
    const start = starts.get(id)
    const detail = event.status === 'running' ? '正在执行' : event.status === 'error' ? '执行失败' : '执行完成'
    const patch: Partial<TraceStep> = {
      status: event.status as TraceStatus,
      detail,
      ...(start !== undefined && event.status !== 'running' ? { durationMs: Math.round(now - start) } : {}),
    }
    if (step) Object.assign(step, patch)
    else trace.push({ id, title, kind, ...patch, detail, status: event.status })
    if (event.status !== 'running') starts.delete(id)
  } else if (event.type === 'sources') {
    trace.push({
      id: 'sources', title: '引用依据', kind: 'context', status: 'success',
      detail: `收到 ${event.sources.length} 条引用依据`,
    })
  } else if (event.type === 'done') {
    finishTrace(trace, 'success', '最终回答已返回')
  } else if (event.type === 'error') {
    finishTrace(trace, 'error', event.message)
  }
}
