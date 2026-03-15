/**
 * AI 服务 API
 * 支持 SSE 流式调用
 */
import { getAccessToken } from './request'

export interface AIGenerateRequest {
  action: 'continue' | 'rewrite' | 'expand' | 'outline' | 'character_analysis' | 'free_chat' | 'analyze_expand' | 'revise' | 'polish_character'
  content: string
  provider?: string
  title?: string
  genre?: string
  description?: string
  question?: string
  chapter_id?: number
}

export interface BatchGenerateRequest {
  chapter_count: number
  words_per_chapter: number
  reference_ids: number[]
  use_knowledge: boolean
}

export interface BatchGenerateEvent {
  type: 'progress' | 'outline' | 'chapter_stream' | 'chapter_done' | 'done' | 'error'
  message?: string
  text?: string
  chapter_index?: number
  title?: string
  chapter_id?: number
  word_count?: number
  total_chapters?: number
}

export interface AIConfig {
  default_provider: string
  available_providers: string[]
  models: Record<string, string>
}

/**
 * 获取 AI 配置
 */
export async function getAIConfig(): Promise<AIConfig> {
  const resp = await fetch('/api/v1/ai/config')
  if (!resp.ok) throw new Error('获取 AI 配置失败')
  return resp.json()
}

/**
 * 流式调用 AI 生成
 * @param projectId 项目 ID
 * @param data 请求参数
 * @param onChunk 每次收到文本块时的回调
 * @param onDone 完成回调
 * @param onError 错误回调
 * @returns AbortController 用于取消请求
 */
export function streamGenerate(
  projectId: number,
  data: AIGenerateRequest,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  fetch(`/api/v1/projects/${projectId}/ai/generate`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '请求失败' }))
        onError(err.detail || '请求失败')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              if (payload.text) {
                onChunk(payload.text)
              }
              if (payload.done) {
                onDone()
                return
              }
              if (payload.error) {
                onError(payload.error)
                return
              }
            } catch {
              // 忽略解析错误
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || '网络请求失败')
      }
    })

  return controller
}

/**
 * 流式批量生成章节
 */
export function streamBatchGenerate(
  projectId: number,
  data: BatchGenerateRequest,
  onEvent: (event: BatchGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  const batchHeaders: Record<string, string> = { 'Content-Type': 'application/json' }
  const batchToken = getAccessToken()
  if (batchToken) {
    batchHeaders['Authorization'] = `Bearer ${batchToken}`
  }

  fetch(`/api/v1/projects/${projectId}/ai/batch-generate`, {
    method: 'POST',
    headers: batchHeaders,
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '请求失败' }))
        onError(err.detail || '请求失败')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6)) as BatchGenerateEvent
              if (payload.type === 'error') {
                onError(payload.message || '生成失败')
                return
              }
              onEvent(payload)
            } catch {
              // 忽略解析错误
            }
          }
        }
      }
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || '网络请求失败')
      }
    })

  return controller
}
