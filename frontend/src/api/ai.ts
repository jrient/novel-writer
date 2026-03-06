/**
 * AI 服务 API
 * 支持 SSE 流式调用
 */

export interface AIGenerateRequest {
  action: 'continue' | 'rewrite' | 'expand' | 'outline' | 'character_analysis' | 'free_chat' | 'analyze_expand'
  content: string
  provider?: string
  title?: string
  genre?: string
  description?: string
  question?: string
  chapter_id?: number
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

  fetch(`/api/v1/projects/${projectId}/ai/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
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
