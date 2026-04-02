/**
 * 扩写模块 API
 * 支持 REST CRUD 和 SSE 流式调用
 */
import request from './request'
import { getAccessToken } from './request'

// ── Types ──

export type ProjectStatus = 'created' | 'analyzed' | 'segmented' | 'expanding' | 'paused' | 'error' | 'completed'
export type SegmentStatus = 'pending' | 'expanding' | 'completed' | 'error' | 'skipped'
export type ExpansionLevel = 'light' | 'medium' | 'deep'
export type SourceType = 'upload' | 'novel' | 'drama' | 'manual'
export type ExecutionMode = 'auto' | 'step_by_step'
export type ConvertTarget = 'novel' | 'drama'

export interface ExpansionAIConfig {
  provider?: string
  model?: string
  temperature?: number
  max_tokens?: number
}

export interface ExpansionProject {
  id: number
  user_id: number
  title: string
  source_type: 'upload' | 'novel' | 'drama' | 'manual'
  word_count: number
  summary: string | null
  style_profile: Record<string, unknown> | null
  expansion_level: 'light' | 'medium' | 'deep'
  target_word_count: number | null
  style_instructions: string | null
  status: 'created' | 'analyzed' | 'segmented' | 'expanding' | 'paused' | 'error' | 'completed'
  execution_mode: 'auto' | 'step_by_step'
  version: number
  created_at: string
  updated_at: string | null
}

export interface ExpansionProjectListItem {
  id: number
  title: string
  source_type: 'upload' | 'novel' | 'drama' | 'manual'
  word_count: number
  expansion_level: 'light' | 'medium' | 'deep'
  status: string
  created_at: string
}

export interface ExpansionSegment {
  id: number
  project_id: number
  sort_order: number
  title: string | null
  original_content: string
  expanded_content: string | null
  expansion_level: 'light' | 'medium' | 'deep' | null
  custom_instructions: string | null
  status: 'pending' | 'expanding' | 'completed' | 'error' | 'skipped'
  error_message: string | null
  original_word_count: number
  expanded_word_count: number | null
  created_at: string
  updated_at: string | null
}

export interface CreateExpansionProjectData {
  title: string
  source_type: 'upload' | 'novel' | 'drama' | 'manual'
  original_text: string
  expansion_level?: 'light' | 'medium' | 'deep'
  target_word_count?: number
  style_instructions?: string
  execution_mode?: 'auto' | 'step_by_step'
  ai_config?: ExpansionAIConfig
}

export interface UpdateExpansionProjectData {
  title?: string
  expansion_level?: 'light' | 'medium' | 'deep'
  target_word_count?: number
  style_instructions?: string
  execution_mode?: 'auto' | 'step_by_step'
  ai_config?: ExpansionAIConfig
  summary?: string
}

export interface ImportFromNovelData {
  project_id: number
  chapter_ids: number[]
  title?: string
}

export interface ImportFromDramaData {
  project_id: number
  title?: string
}

export interface SegmentSplitData {
  segment_id: number
  split_position: number
}

export interface SegmentMergeData {
  segment_ids: number[]
}

export interface ConvertData {
  target: 'novel' | 'drama'
}

export interface UpdateSegmentData {
  title?: string
  expansion_level?: 'light' | 'medium' | 'deep'
  custom_instructions?: string
}

// ── SSE Stream Callbacks ──

export interface StreamCallbacks {
  onText?: (text: string) => void
  onEvent?: (type: string, data: unknown) => void
  onDone?: (data?: unknown) => void
  onError?: (message: string) => void
}

// ── Project API ──

export async function getExpansionProjects(params?: {
  status?: string
  expansion_level?: string
  page?: number
  page_size?: number
}): Promise<ExpansionProjectListItem[]> {
  const res = await request.get<{ items: ExpansionProjectListItem[] }>('/expansion/', { params })
  return res.items
}

export async function createExpansionProject(data: CreateExpansionProjectData): Promise<ExpansionProject> {
  return request.post<ExpansionProject>('/expansion/', data)
}

export async function uploadExpansionProject(
  file: File,
  title?: string,
  expansion_level?: 'light' | 'medium' | 'deep',
  target_word_count?: number,
  style_instructions?: string,
  execution_mode?: 'auto' | 'step_by_step',
): Promise<ExpansionProject> {
  const formData = new FormData()
  formData.append('file', file)
  if (title) formData.append('title', title)
  if (expansion_level) formData.append('expansion_level', expansion_level)
  if (target_word_count) formData.append('target_word_count', String(target_word_count))
  if (style_instructions) formData.append('style_instructions', style_instructions)
  if (execution_mode) formData.append('execution_mode', execution_mode)

  return request.post<ExpansionProject>('/expansion/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function importFromNovel(data: ImportFromNovelData): Promise<ExpansionProject> {
  return request.post<ExpansionProject>('/expansion/import', { source: 'novel', ...data })
}

export async function importFromDrama(data: ImportFromDramaData): Promise<ExpansionProject> {
  return request.post<ExpansionProject>('/expansion/import', { source: 'drama', ...data })
}

export async function getExpansionProject(id: number): Promise<ExpansionProject> {
  return request.get<ExpansionProject>(`/expansion/${id}`)
}

export async function updateExpansionProject(id: number, data: UpdateExpansionProjectData): Promise<ExpansionProject> {
  return request.put<ExpansionProject>(`/expansion/${id}`, data)
}

export async function deleteExpansionProject(id: number): Promise<void> {
  return request.delete(`/expansion/${id}`)
}

// ── Analysis (SSE) ──

export function streamAnalyzeProject(id: number, callbacks: StreamCallbacks): AbortController {
  return _expansionStreamRequest(`/api/v1/expansion/${id}/analyze`, {}, callbacks)
}

export function streamResegmentProject(id: number, callbacks: StreamCallbacks): AbortController {
  return _expansionStreamRequest(`/api/v1/expansion/${id}/resegment`, {}, callbacks)
}

// ── Segments ──

export async function getSegments(projectId: number): Promise<ExpansionSegment[]> {
  return request.get<ExpansionSegment[]>(`/expansion/${projectId}/segments`)
}

export async function updateSegment(
  projectId: number,
  segId: number,
  data: UpdateSegmentData,
): Promise<ExpansionSegment> {
  return request.put<ExpansionSegment>(`/expansion/${projectId}/segments/${segId}`, data)
}

export async function splitSegment(
  projectId: number,
  data: SegmentSplitData,
): Promise<ExpansionSegment[]> {
  return request.post<ExpansionSegment[]>(`/expansion/${projectId}/segments/split`, data)
}

export async function mergeSegments(
  projectId: number,
  data: SegmentMergeData,
): Promise<ExpansionSegment> {
  return request.post<ExpansionSegment>(`/expansion/${projectId}/segments/merge`, data)
}

export async function reorderSegments(projectId: number, order: number[]): Promise<void> {
  return request.put(`/expansion/${projectId}/segments/reorder`, { segment_ids: order })
}

// ── Expansion (SSE) ──

export function streamExpandProject(id: number, callbacks: StreamCallbacks): AbortController {
  return _expansionStreamRequest(`/api/v1/expansion/${id}/expand`, {}, callbacks)
}

export function streamExpandSegment(
  projectId: number,
  segId: number,
  callbacks: StreamCallbacks,
  data?: { expansion_level?: 'light' | 'medium' | 'deep'; custom_instructions?: string },
): AbortController {
  return _expansionStreamRequest(
    `/api/v1/expansion/${projectId}/segments/${segId}/expand`,
    data || {},
    callbacks,
  )
}

export async function pauseExpansion(id: number): Promise<void> {
  return request.post(`/expansion/${id}/pause`)
}

export function streamResumeExpansion(id: number, callbacks: StreamCallbacks): AbortController {
  return _expansionStreamRequest(`/api/v1/expansion/${id}/resume`, {}, callbacks)
}

export function streamRetrySegment(
  projectId: number,
  segId: number,
  callbacks: StreamCallbacks,
): AbortController {
  return _expansionStreamRequest(
    `/api/v1/expansion/${projectId}/segments/${segId}/retry`,
    {},
    callbacks,
  )
}

export function streamResegmentSegments(
  projectId: number,
  segmentIds: number[],
  callbacks: StreamCallbacks,
): AbortController {
  return _expansionStreamRequest(
    `/api/v1/expansion/${projectId}/segments/resegment`,
    { segment_ids: segmentIds },
    callbacks,
  )
}

// ── Export & Convert ──

export function getExportUrl(
  id: number,
  format: 'txt' | 'md' | 'docx',
  version: 'original' | 'expanded' | 'both',
): string {
  return `/api/v1/expansion/${id}/export?format=${format}&version=${version}`
}

export async function convertProject(
  id: number,
  data: ConvertData,
): Promise<{ project_id: number; project_type: string }> {
  return request.post(`/expansion/${id}/convert`, data)
}

// ── Internal SSE helper ──

function _expansionStreamRequest(
  url: string,
  body: Record<string, unknown>,
  callbacks: StreamCallbacks,
  timeoutMs: number = 600000, // 默认 10 分钟超时（长文本分析可能需要）
): AbortController {
  const controller = new AbortController()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // 设置整体超时
  const timeoutId = setTimeout(() => {
    controller.abort()
    callbacks.onError?.('请求超时，文本过长或服务器响应过慢')
  }, timeoutMs)

  fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: controller.signal,
    credentials: 'same-origin',
  })
    .then(async (response) => {
      console.log('[SSE] Response status:', response.status, 'headers:', Array.from(response.headers.entries()))
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '请求失败' }))
        callbacks.onError?.(err.detail || '请求失败')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        callbacks.onError?.('无法读取响应流')
        return
      }
      console.log('[SSE] Reader acquired, starting to read stream...')

      const decoder = new TextDecoder()
      let buffer = ''
      // TTFB 超时：首字节最多等 60 秒
      const TTFB_TIMEOUT = 60000
      // 读取超时：后续每块数据最多等 180 秒
      const READ_TIMEOUT = 180000

      let readTimeoutId: ReturnType<typeof setTimeout> | null = null
      let isFirstChunk = true

      const resetReadTimeout = () => {
        if (readTimeoutId) clearTimeout(readTimeoutId)
        readTimeoutId = setTimeout(() => {
          controller.abort()
          callbacks.onError?.('服务器响应超时，AI 模型可能过慢或网络不稳定')
        }, READ_TIMEOUT)
      }

      // 首字节超时检测
      const ttfbTimeoutId = setTimeout(() => {
        if (isFirstChunk) {
          controller.abort()
          callbacks.onError?.('AI 响应超时（60 秒未收到首字节），请重试或检查 AI 服务状态')
        }
      }, TTFB_TIMEOUT)

      resetReadTimeout()

      while (true) {
        const { done, value } = await reader.read()
        console.log('[SSE] Read chunk:', { done, valueLength: value?.length })
        if (done) break

        if (isFirstChunk) {
          clearTimeout(ttfbTimeoutId)
          isFirstChunk = false
        }

        resetReadTimeout()

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              const { type, text, ...rest } = payload

              if (text !== undefined) {
                callbacks.onText?.(text)
              }

              if (type === 'done') {
                if (readTimeoutId) clearTimeout(readTimeoutId)
                callbacks.onDone?.(rest)
                return
              }

              if (type === 'error') {
                if (readTimeoutId) clearTimeout(readTimeoutId)
                callbacks.onError?.(payload.message || '发生错误')
                return
              }

              // Handle all other event types: status, segments, segment_start, segment_done, await_confirm, phase
              if (type) {
                callbacks.onEvent?.(type, payload)
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
      if (readTimeoutId) clearTimeout(readTimeoutId)
      if (ttfbTimeoutId) clearTimeout(ttfbTimeoutId)
      callbacks.onDone?.()
    })
    .catch((err) => {
      console.error('[SSE] Fetch error:', err)
      if (err.name !== 'AbortError') {
        callbacks.onError?.(err.message || '网络请求失败')
      }
    })
    .finally(() => {
      clearTimeout(timeoutId)
    })

  return controller
}