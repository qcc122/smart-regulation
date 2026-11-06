import { ref } from 'vue'
import { ragApi } from '../api/rag'
import type { DocumentItem, SourceItem, TraceStep } from '../types/rag'
import type { useTypewriter } from './use-typewriter'
import { useToast } from './use-toast'

type HealthStatus = 'online' | 'offline' | 'checking'

const MAX_UPLOAD_MB = 20
const ALLOWED_EXTENSIONS = ['.pdf', '.docx']

// 模块级单例：跨视图共享的应用状态
const health = ref<HealthStatus>('checking')
const documents = ref<DocumentItem[]>([])
const documentsLoading = ref(false)
const isUploading = ref(false)
const isDemo = ref(false)
const topK = ref(5)
const currentSources = ref<SourceItem[]>([])
const currentTrace = ref<TraceStep[]>([])
const streamingId = ref<string | null>(null)
const streamPaused = ref(false)

let typewriter: ReturnType<typeof useTypewriter> | null = null
let abortController: AbortController | null = null

export function useAppState() {
  const { notify } = useToast()

  async function checkHealth(): Promise<void> {
    if (isDemo.value) {
      health.value = 'offline'
      return
    }
    health.value = 'checking'
    try {
      await ragApi.checkHealth()
      health.value = 'online'
    } catch {
      health.value = 'offline'
    }
  }

  async function refreshDocuments(): Promise<void> {
    if (isDemo.value) {
      documents.value = []
      return
    }
    documentsLoading.value = true
    try {
      documents.value = await ragApi.listDocuments()
    } catch {
      documents.value = []
    } finally {
      documentsLoading.value = false
    }
  }

  async function handleUpload(file: File): Promise<void> {
    const lower = file.name.toLowerCase()
    if (!ALLOWED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
      notify('仅支持 PDF / DOCX 格式文件', 'error')
      return
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      notify(`文件大小不能超过 ${MAX_UPLOAD_MB}MB`, 'error')
      return
    }
    if (isDemo.value) {
      notify('演示模式不支持上传，请先退出演示', 'error')
      return
    }
    isUploading.value = true
    try {
      const result = await ragApi.uploadDocument(file)
      notify(`${result.filename} 已入库，切分为 ${result.chunk_count} 个片段`, 'success')
      await refreshDocuments()
    } catch (error) {
      notify(`上传失败：${error instanceof Error ? error.message : '未知错误'}`, 'error')
    } finally {
      isUploading.value = false
    }
  }

  async function handleRemoveDocument(docId: string): Promise<void> {
    try {
      await ragApi.deleteDocument(docId)
      notify(`文档 ${docId} 已删除`, 'success')
      await refreshDocuments()
    } catch (error) {
      notify(`删除失败：${error instanceof Error ? error.message : '未知错误'}`, 'error')
    }
  }

  function toggleDemo(): void {
    if (streamingId.value) {
      notify('回答生成中，请先停止再切换模式', 'error')
      return
    }
    isDemo.value = !isDemo.value
    if (isDemo.value) {
      health.value = 'offline'
      notify('已切换到演示模式，使用样例数据展示界面')
    } else {
      void checkHealth()
      void refreshDocuments()
      notify('已切换到真实接口模式')
    }
  }

  function bindStream(tw: ReturnType<typeof useTypewriter> | null, controller: AbortController | null): void {
    typewriter = tw
    abortController = controller
  }

  function releaseStream(): void {
    typewriter?.dispose()
    typewriter = null
    abortController = null
    streamingId.value = null
    streamPaused.value = false
  }

  function pauseStream(): void {
    typewriter?.pause()
    streamPaused.value = true
  }

  function resumeStream(): void {
    typewriter?.resume()
    streamPaused.value = false
  }

  function skipStream(): void {
    typewriter?.skip()
    streamPaused.value = false
  }

  function stopStream(): void {
    abortController?.abort()
    typewriter?.stop()
    streamPaused.value = false
  }

  return {
    health,
    documents,
    documentsLoading,
    isUploading,
    isDemo,
    topK,
    currentSources,
    currentTrace,
    streamingId,
    streamPaused,
    checkHealth,
    refreshDocuments,
    handleUpload,
    handleRemoveDocument,
    toggleDemo,
    bindStream,
    releaseStream,
    pauseStream,
    resumeStream,
    skipStream,
    stopStream,
  }
}