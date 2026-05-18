import request from './request'
import type { ScoreDocxResponse } from './rubric'

export type EntityType = 'person' | 'place' | 'prop' | 'era_term' | 'other'

export interface MappingEntry {
  id?: number
  entity_type: EntityType
  original_text: string
  replacement_text?: string | null
  locked: boolean
  notes?: string | null
  order_index: number
}

export interface SceneBoundary {
  index: number
  start: number
  end: number
  title: string
}

export interface AdaptationVersion {
  id: number
  version_no: number
  triggered_by: string
  status: 'running' | 'done' | 'partial' | 'failed'
  stats?: any
  error?: string | null
  created_at: string
  completed_at?: string | null
}

export interface SceneResult {
  id: number
  scene_index: number
  scene_title?: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'manual_edited'
  error?: string | null
  token_used?: number
  line_count_delta_pct?: number | null
  original_scene_text: string
  rewritten_scene_text?: string | null
  manual_edits?: any[]
  updated_at: string
}

export interface AdaptationProject {
  id: number
  title: string
  source_filename?: string
  intent?: string | null
  intensity: number
  era_target?: string | null
  status: string
  created_at: string
  updated_at: string
  word_count: number
  scene_boundaries: SceneBoundary[]
  versions: AdaptationVersion[]
  mappings: MappingEntry[]
}

const base = '/adaptation'

export const adaptationApi = {
  list: () => request.get<AdaptationProject[]>(`${base}/projects`),
  get: (id: number) => request.get<AdaptationProject>(`${base}/projects/${id}`),
  createWithText: (payload: {title: string; raw_text: string; intent?: string; intensity: number; era_target?: string}) =>
    request.post<AdaptationProject>(`${base}/projects`, payload),
  createWithUpload: (form: FormData) =>
    request.post<AdaptationProject>(`${base}/projects/upload`, form, {
      headers: {'Content-Type': 'multipart/form-data'},
    }),
  update: (id: number, payload: Partial<{title: string; intent: string; intensity: number; era_target: string}>) =>
    request.patch<AdaptationProject>(`${base}/projects/${id}`, payload),
  remove: (id: number) => request.delete(`${base}/projects/${id}`),
  extract: (id: number) => request.post<AdaptationProject>(`${base}/projects/${id}/extract`),
  split: (id: number) => request.post<AdaptationProject>(`${base}/projects/${id}/split`),
  putMappings: (id: number, entries: MappingEntry[]) =>
    request.put<MappingEntry[]>(`${base}/projects/${id}/mappings`, {entries}),
  suggestMappings: (id: number) =>
    request.post<MappingEntry[]>(`${base}/projects/${id}/mappings/suggest`, {only_empty: true}),
  createRun: (id: number, extra_prompt?: string) =>
    request.post<AdaptationVersion>(`${base}/projects/${id}/runs`, {extra_prompt}),
  listRuns: (id: number) => request.get<AdaptationVersion[]>(`${base}/projects/${id}/runs`),
  getRun: (vid: number) =>
    request.get<AdaptationVersion & {scene_results: SceneResult[]}>(`${base}/runs/${vid}`),
  rerunScene: (vid: number, idx: number, extra_prompt?: string) =>
    request.post<SceneResult>(`${base}/runs/${vid}/scenes/${idx}/rerun`, {extra_prompt}),
  patchScene: (vid: number, idx: number, rewritten: string) =>
    request.patch<SceneResult>(`${base}/runs/${vid}/scenes/${idx}`, {rewritten_scene_text: rewritten}),
  exportUrl: (vid: number, format: 'txt' | 'docx') =>
    `/api/v1/adaptation/runs/${vid}/export?format=${format}`,
  getStreamTicket: (vid: number) =>
    request.post<{ticket: string}>(`${base}/runs/${vid}/stream/ticket`),
  streamUrl: (vid: number, ticket: string) =>
    `/api/v1/adaptation/runs/${vid}/stream?ticket=${encodeURIComponent(ticket)}`,
  /** 用 script_rubric handbook 对当前版本拼接出来的全剧本做即时评分 */
  scoreRun: (vid: number) =>
    request.post<ScoreDocxResponse>(`${base}/runs/${vid}/score`),
}
