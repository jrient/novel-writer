import request from './request'

export type CanonEntityType =
  | 'character' | 'location' | 'ability' | 'faction' | 'worldrule'
  | 'event' | 'item' | 'race' | 'realm' | 'concept'

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

export type CanonRelationReview =
  | 'ai_extracted' | 'user_verified' | 'user_edited' | 'user_added'

export interface CanonRelation {
  id: number
  reference_id: number
  source_entity_id: number
  target_entity_id: number
  relation_type: string
  label: string | null
  summary: string | null
  source_refs: CanonSourceRef[]
  confidence: number
  review_status: CanonRelationReview
  created_at: string
  updated_at: string | null
}

export interface CanonGraph {
  nodes: CanonEntity[]
  edges: CanonRelation[]
}

export interface CanonRelationCreate {
  source_entity_id: number
  target_entity_id: number
  relation_type: string
  label?: string | null
  summary?: string | null
  source_refs?: CanonSourceRef[]
}

export interface CanonRelationUpdate {
  relation_type?: string
  label?: string | null
  summary?: string | null
  review_status?: CanonRelationReview
}

export const canonApi = {
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

  getGraph(refId: number) {
    return request.get<CanonGraph>(`/references/${refId}/canon/graph`)
  },

  listRelations(refId: number) {
    return request.get<CanonRelation[]>(`/references/${refId}/canon/relations`)
  },

  createRelation(refId: number, data: CanonRelationCreate) {
    return request.post<CanonRelation>(`/references/${refId}/canon/relations`, data)
  },

  updateRelation(refId: number, id: number, data: CanonRelationUpdate) {
    return request.put<CanonRelation>(`/references/${refId}/canon/relations/${id}`, data)
  },

  deleteRelation(refId: number, id: number) {
    return request.delete(`/references/${refId}/canon/relations/${id}`)
  },

  extractRelations(refId: number) {
    return request.post(`/references/${refId}/canon/extract-relations`, undefined, { skipErrorToast: true })
  },
}
