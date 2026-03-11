/**
 * 向导模块 API
 * 支持创作向导的 SSE 流式调用
 */

export interface WizardGenerateRequest {
  title: string
  genre?: string
  description: string
  target_word_count: number
  chapter_count: number
  reference_ids?: number[]
}

export interface ChapterOutlineItem {
  chapter: number
  title: string
  summary: string
}

export interface CharacterOutlineItem {
  name: string
  role_type: string
  gender?: string
  age?: string
  occupation?: string
  personality_traits?: string
  appearance?: string
  background?: string
}

export interface WizardCreateRequest {
  title: string
  genre?: string
  description?: string
  target_word_count: number
  outline: ChapterOutlineItem[]
  characters: CharacterOutlineItem[]
  reference_ids?: number[]
}

export interface WizardCreateResponse {
  project_id: number
  message: string
}

export interface WizardGenerateEvent {
  type: 'progress' | 'outline' | 'characters' | 'done' | 'error'
  message?: string
  data?: ChapterOutlineItem[] | CharacterOutlineItem[]
}

/**
 * 流式调用向导生成
 */
export function streamWizardGenerate(
  data: WizardGenerateRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  fetch('/api/v1/wizard/generate', {
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
              const payload = JSON.parse(line.slice(6)) as WizardGenerateEvent
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

/**
 * 创建向导项目
 */
export async function createWizardProject(data: WizardCreateRequest): Promise<WizardCreateResponse> {
  const resp = await fetch('/api/v1/wizard/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '创建失败' }))
    throw new Error(err.detail || '创建失败')
  }
  return resp.json()
}