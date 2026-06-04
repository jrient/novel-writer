import request from './request'

export type CanonEntityType =
  | 'character'
  | 'location'
  | 'ability'
  | 'faction'
  | 'worldrule'
  | 'event'

export type CanonImportance = 'critical' | 'major' | 'minor'

export type CanonReviewStatus =
  | 'ai_extracted'
  | 'user_verified'
  | 'user_edited'
  | 'user_added'

export type CanonJobStatus = 'pending' | 'processing' | 'done' | 'failed'

export interface CanonSourceRef {
  chapter?: number | string
  offset?: number
  quote?: string
}

export interface CanonEntity {
  id: number
  reference_id: number
  entity_type: CanonEntityType
  canonical_name: string
  aliases: string[]
  summary: string | null
  attributes: Record<string, unknown>
  source_refs: CanonSourceRef[]
  importance: CanonImportance
  confidence: number
  review_status: CanonReviewStatus
  created_at: string
  updated_at: string | null
}

export interface CanonJob {
  id: number
  reference_id: number
  status: CanonJobStatus
  model?: string | null
  chunk_total: number
  chunk_done: number
  failed_chunks: number
  entity_count: number
  error?: string | null
  created_at: string
  updated_at: string | null
}

export interface CanonEntityCreate {
  entity_type: CanonEntityType
  canonical_name: string
  aliases: string[]
  summary?: string | null
  attributes: Record<string, unknown>
  source_refs: CanonSourceRef[]
  importance?: CanonImportance
}

export interface CanonEntityUpdate {
  canonical_name?: string
  aliases?: string[]
  summary?: string | null
  attributes?: Record<string, unknown>
  importance?: CanonImportance
  review_status?: CanonReviewStatus
}

export const canonApi = {
  // 触发提取，202；若已有进行中任务返回 409（调用方据 error.response.status 判断，
  // skipErrorToast 让 409 不弹全局错误提示——这是正常的“接管在跑任务”路径）。
  extract(refId: number) {
    return request.post(`/references/${refId}/canon/extract`, undefined, { skipErrorToast: true })
  },

  getJob(refId: number) {
    return request.get<CanonJob>(`/references/${refId}/canon/job`)
  },

  listEntities(refId: number) {
    return request.get<CanonEntity[]>(`/references/${refId}/canon/entities`)
  },

  createEntity(refId: number, data: CanonEntityCreate) {
    return request.post<CanonEntity>(`/references/${refId}/canon/entities`, data)
  },

  updateEntity(refId: number, entityId: number, data: CanonEntityUpdate) {
    return request.put<CanonEntity>(`/references/${refId}/canon/entities/${entityId}`, data)
  },

  deleteEntity(refId: number, entityId: number) {
    return request.delete(`/references/${refId}/canon/entities/${entityId}`)
  },

  getStreamTicket(refId: number) {
    return request.post<{ ticket: string }>(`/references/${refId}/canon/stream/ticket`)
  },

  getStreamUrl(refId: number, ticket: string): string {
    const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    return `${base}/api/v1/references/${refId}/canon/stream?ticket=${encodeURIComponent(ticket)}`
  },
}
