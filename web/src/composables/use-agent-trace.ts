import type { TraceStep } from '../types/rag'

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