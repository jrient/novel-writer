/**
 * 剧本模块 API
 * 支持 REST CRUD 和 SSE 流式调用
 */
import request, { authedFetch } from './request'

// ── Types ──

export interface AIPromptConfig {
  questioning?: string
  outlining?: string
  expanding?: string
  rewriting?: string
}

export interface AIConfig {
  provider?: string
  model?: string
  temperature?: number
  max_tokens?: number
  prompts?: AIPromptConfig
}

export interface CharacterSetting {
  id: string
  name: string
  description: string
}

export interface ProjectSettings {
  characters: CharacterSetting[]
  world_setting: string
  tone: string
  plot_anchors: string
  persistent_directive: string
}

export const defaultProjectSettings: ProjectSettings = {
  characters: [],
  world_setting: '',
  tone: '',
  plot_anchors: '',
  persistent_directive: '',
}

export interface ScriptProject {
  id: number
  user_id: number
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  status: 'drafting' | 'outlined' | 'writing' | 'completed'
  ai_config: AIConfig | null
  metadata_: Record<string, unknown> | null
  created_at: string
  updated_at: string | null
}

export interface ScriptProjectListItem {
  id: number
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  status: string
  created_at: string
  updated_at: string | null
}

export interface CreateScriptProjectData {
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  ai_config?: AIConfig
  metadata?: Record<string, unknown>
}

export interface UpdateScriptProjectData {
  title?: string
  concept?: string
  status?: string
  metadata?: Record<string, unknown>
}

export interface ScriptNode {
  id: number
  project_id: number
  parent_id: number | null
  node_type: string
  title: string | null
  content: string | null
  speaker: string | null
  visual_desc: string | null
  sort_order: number
  is_completed: boolean
  metadata_: Record<string, unknown> | null
  created_at: string
  updated_at: string | null
  children?: ScriptNode[]
}

export interface CreateNodeData {
  parent_id?: number | null
  node_type: string
  title?: string
  content?: string
  speaker?: string
  visual_desc?: string
  sort_order?: number
  metadata?: Record<string, unknown>
}

export interface UpdateNodeData {
  title?: string
  content?: string
  speaker?: string
  visual_desc?: string
  sort_order?: number
  is_completed?: boolean
  metadata?: Record<string, unknown>
}

export interface ReorderItem {
  id: number
  sort_order: number
  parent_id?: number | null
}

export interface SessionSummary {
  故事概要: string
  主要角色: string[]
  核心冲突: string
  场景设定: string
  风格基调: string
  目标集数: number
  主角弱点?: string
  反派逻辑?: string
  开局钩子?: string
}

export interface ScriptSession {
  id: number
  project_id: number
  state: 'init' | 'collecting' | 'generating' | 'done'
  history: Array<{ role: string; content: string }> | null
  outline_draft: Record<string, unknown> | null
  summary: SessionSummary | null
  current_node_id: number | null
  created_at: string
  updated_at: string | null
}

// ── Project API ──

export async function getDramaProjects(params?: {
  script_type?: string
  status?: string
  page?: number
  page_size?: number
}): Promise<ScriptProjectListItem[]> {
  const res = await request.get<{ items: ScriptProjectListItem[] }>('/drama/', { params })
  return res.items
}

export async function createDramaProject(data: CreateScriptProjectData): Promise<ScriptProject> {
  return request.post<ScriptProject>('/drama/', data)
}

export async function getDramaProject(id: number): Promise<ScriptProject> {
  return request.get<ScriptProject>(`/drama/${id}`)
}

export async function updateDramaProject(id: number, data: UpdateScriptProjectData): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}`, data)
}

export async function deleteDramaProject(id: number): Promise<void> {
  return request.delete(`/drama/${id}`)
}

export async function updateAIConfig(id: number, data: AIConfig): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}/ai-config`, { ai_config: data })
}

export async function updateProjectSettings(id: number, data: ProjectSettings): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}/settings`, data)
}

// ── Node API ──

export async function getNodes(projectId: number): Promise<ScriptNode[]> {
  return request.get<ScriptNode[]>(`/drama/${projectId}/nodes`)
}

export async function createNode(projectId: number, data: CreateNodeData): Promise<ScriptNode> {
  return request.post<ScriptNode>(`/drama/${projectId}/nodes`, data)
}

export async function updateNode(projectId: number, nodeId: number, data: UpdateNodeData): Promise<ScriptNode> {
  return request.put<ScriptNode>(`/drama/${projectId}/nodes/${nodeId}`, data)
}

export async function deleteNode(projectId: number, nodeId: number): Promise<void> {
  return request.delete(`/drama/${projectId}/nodes/${nodeId}`)
}

export async function reorderNodes(projectId: number, orders: ReorderItem[]): Promise<void> {
  return request.put(`/drama/${projectId}/nodes/reorder`, { node_ids: orders.map((o: ReorderItem) => o.id) })
}

// ── Session API ──

export async function getOrCreateSession(projectId: number): Promise<ScriptSession> {
  return request.post<ScriptSession>(`/drama/${projectId}/session`)
}

export async function deleteSession(projectId: number): Promise<void> {
  return request.delete(`/drama/${projectId}/session`)
}

export async function skipToOutline(projectId: number): Promise<{ ok: boolean }> {
  return request.post(`/drama/${projectId}/session/skip`)
}

export async function confirmOutline(projectId: number): Promise<{ ok: boolean }> {
  return request.post(`/drama/${projectId}/session/confirm-outline`)
}

// ── SSE Streaming ──

export function streamSessionInit(
  projectId: number,
  onChunk: (text: string) => void,
  onDone: (fullResponse?: unknown) => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/init`,
    {},
    onChunk,
    onDone,
    onError,
  )
}

export function streamSessionAnswer(
  projectId: number,
  content: string,
  onChunk: (text: string) => void,
  onDone: (fullResponse?: unknown) => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/answer`,
    { answer: content },
    onChunk,
    onDone,
    onError,
  )
}

export function streamGenerateOutline(
  projectId: number,
  onChunk: (text: string) => void,
  onDone: (outline?: unknown) => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/generate-outline`,
    {},
    onChunk,
    onDone,
    onError,
  )
}

export function streamExpandEpisode(
  projectId: number,
  episodeIndex: number,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/expand-episode`,
    { episode_index: episodeIndex },
    onChunk,
    onDone,
    onError,
  )
}

export function streamExpandNode(
  projectId: number,
  nodeId: number,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
  instruction?: string,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/nodes/${nodeId}/expand`,
    instruction ? { instructions: instruction } : {},
    onChunk,
    onDone,
    onError,
  )
}

export function streamRewrite(
  projectId: number,
  data: { node_id: number; instructions: string },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/ai/rewrite`,
    data,
    onChunk,
    onDone,
    onError,
  )
}

export function streamGlobalDirective(
  projectId: number,
  data: { directive: string; scope?: string; node_ids?: number[] },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/ai/global-directive`,
    data,
    onChunk,
    onDone,
    onError,
  )
}

// ── Export ──

export function getExportUrl(projectId: number, format: 'txt' | 'markdown'): string {
  return `/api/v1/drama/${projectId}/export?format=${format}`
}

export async function summarizeSession(projectId: number): Promise<SessionSummary> {
  return request.post<SessionSummary>(`/drama/${projectId}/session/summarize`)
}

export async function updateSessionSummary(projectId: number, summary: SessionSummary): Promise<SessionSummary> {
  return request.put<SessionSummary>(`/drama/${projectId}/session/summary`, summary)
}

// ── Internal SSE helper ──

function _streamRequest(
  url: string,
  body: Record<string, unknown>,
  onChunk: (text: string) => void,
  onDone: (data?: unknown) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()

  authedFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
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

      try {
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
                if (payload.type === 'error') {
                  onError(payload.message)
                  return
                }
                if (payload.type === 'done') {
                  onDone(payload.outline || payload.full_response)
                  return
                }
                if (payload.text) onChunk(payload.text)
              } catch {
                // ignore parse errors
              }
            }
          }
        }
      } catch (err) {
        // Connection dropped unexpectedly (network error, timeout, etc.)
        onError(err instanceof Error ? err.message : '连接意外断开')
        return
      }

      // Process remaining buffer after stream ends
      if (buffer.startsWith('data: ')) {
        try {
          const payload = JSON.parse(buffer.slice(6))
          if (payload.type === 'done') {
            onDone(payload.outline || payload.full_response)
            return
          }
          if (payload.type === 'error') {
            onError(payload.message)
            return
          }
        } catch {
          // ignore parse errors
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

// ── Node Version API ──

export interface NodeVersion {
  id: number
  node_id: number
  version_number: number
  title: string | null
  content: string | null
  source: 'init' | 'ai_apply' | 'switch' | 'manual'
  created_at: string
}

export async function listNodeVersions(projectId: number, nodeId: number): Promise<NodeVersion[]> {
  return request.get<NodeVersion[]>(`/drama/${projectId}/nodes/${nodeId}/versions`)
}

export async function createNodeVersion(projectId: number, nodeId: number, source: string): Promise<NodeVersion> {
  return request.post<NodeVersion>(`/drama/${projectId}/nodes/${nodeId}/versions`, { source })
}

export async function restoreNodeVersion(projectId: number, nodeId: number, versionId: number): Promise<NodeVersion> {
  return request.post<NodeVersion>(`/drama/${projectId}/nodes/${nodeId}/versions/${versionId}/restore`)
}
