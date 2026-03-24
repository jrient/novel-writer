/**
 * 向导模块 API
 * 支持创作向导的 SSE 流式调用
 * 支持新的地图-部分-章节层级结构
 */
import { getAccessToken } from './request'

// ============ UUID 生成工具 ============

export function generateUUID(): string {
  return crypto.randomUUID ? crypto.randomUUID().slice(0, 8) :
    Math.random().toString(36).slice(2, 10)
}

// ============ 新的数据结构 ============

export interface SceneNode {
  id?: string
  name: string
  description?: string
}

export interface ChapterOutlineItem {
  id?: string
  chapter: number
  title: string
  summary: string
  scenes?: SceneNode[]
}

export interface PartNode {
  id?: string
  name: string
  summary?: string
  chapters: ChapterOutlineItem[]
  character_ids: string[]
}

export interface MapNode {
  id?: string
  name: string
  description?: string
  parts: PartNode[]
}

export interface CharacterOutlineItem {
  id?: string
  name: string
  role_type: string
  gender?: string
  age?: string
  occupation?: string
  personality_traits?: string
  appearance?: string
  background?: string
  appearances?: string[]
  origin_map_id?: string  // 初次登场的地图ID
  is_new?: boolean
}

export interface NoteItem {
  id?: string
  note_type: 'foreshadowing' | 'inspiration' | 'note'
  title: string
  content?: string
  related_chapter_ids?: string[]
  target_type?: 'map' | 'part' | 'chapter'  // 关联目标类型
  target_id?: string  // 关联目标ID
  status?: 'active' | 'resolved' | 'abandoned'
}

// ============ 新的请求/响应类型 ============

export interface WizardMapsRequest {
  title: string
  genre?: string
  description: string
  reference_ids?: number[]
  revision_request?: string
  current_maps?: MapNode[]
}

export interface WizardPartsRequest {
  title: string
  genre?: string
  description: string
  map_id: string
  map_name: string
  revision_request?: string
  current_parts?: PartNode[]
}

export interface WizardCharactersForPartRequest {
  title: string
  genre?: string
  description: string
  parts: PartNode[]
  existing_characters?: CharacterOutlineItem[]
}

export interface WizardCreateV2Request {
  title: string
  genre?: string
  description?: string
  maps: MapNode[]
  characters: CharacterOutlineItem[]
  notes?: NoteItem[]
  reference_ids?: number[]
}

export interface WizardCreateResponse {
  project_id: number
  message: string
}

// ============ 旧接口类型（保留兼容） ============

export interface WizardGenerateRequest {
  title: string
  genre?: string
  description: string
  target_word_count: number
  chapter_count: number
  reference_ids?: number[]
  revision_request?: string
  current_outline?: ChapterOutlineItem[]
  current_characters?: CharacterOutlineItem[]
}

export interface WizardOutlineRequest {
  title: string
  genre?: string
  description: string
  target_word_count: number
  chapter_count: number
  reference_ids?: number[]
  revision_request?: string
  current_outline?: ChapterOutlineItem[]
}

export interface WizardCharactersRequest {
  title: string
  genre?: string
  description: string
  outline: ChapterOutlineItem[]
}

export interface WizardCreateRequest {
  title: string
  genre?: string
  description?: string
  target_word_count: number
  outline: ChapterOutlineItem[]
  characters: CharacterOutlineItem[]
  reference_ids?: number[]
  outline_text?: string
}

// ============ SSE 事件类型 ============

export interface WizardGenerateEvent {
  type: 'progress' | 'outline' | 'characters' | 'maps' | 'parts' | 'done' | 'error'
  message?: string
  data?: any
}

// ============ SSE 流式调用工具函数 ============

function createSSEStream(
  url: string,
  data: any,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  fetch(url, {
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

// ============ 新的 API 函数 ============

/**
 * 步骤2：生成地图大纲（SSE 流式）
 */
export function streamWizardMaps(
  data: WizardMapsRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate-maps', data, onEvent, onError)
}

/**
 * 步骤3：为地图生成部分（SSE 流式）
 */
export function streamWizardParts(
  data: WizardPartsRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate-parts', data, onEvent, onError)
}

/**
 * 步骤4：为部分生成角色（SSE 流式）
 */
export function streamWizardCharactersForPart(
  data: WizardCharactersForPartRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate-characters-for-part', data, onEvent, onError)
}

/**
 * 创建向导项目（新版本）
 */
export async function createWizardProjectV2(data: WizardCreateV2Request): Promise<WizardCreateResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const resp = await fetch('/api/v1/wizard/create-v2', {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '创建失败' }))
    throw new Error(err.detail || '创建失败')
  }
  return resp.json()
}

// ============ 旧 API 函数（保留兼容） ============

export function streamWizardGenerate(
  data: WizardGenerateRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate', data, onEvent, onError)
}

export function streamWizardOutline(
  data: WizardOutlineRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate-outline', data, onEvent, onError)
}

export function streamWizardCharacters(
  data: WizardCharactersRequest,
  onEvent: (event: WizardGenerateEvent) => void,
  onError: (error: string) => void,
): AbortController {
  return createSSEStream('/api/v1/wizard/generate-characters', data, onEvent, onError)
}

export async function createWizardProject(data: WizardCreateRequest): Promise<WizardCreateResponse> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const resp = await fetch('/api/v1/wizard/create', {
    method: 'POST',
    headers,
    body: JSON.stringify(data),
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '创建失败' }))
    throw new Error(err.detail || '创建失败')
  }
  return resp.json()
}