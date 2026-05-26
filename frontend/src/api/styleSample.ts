import request from './request'

export type IndexStatus = 'pending' | 'indexing' | 'ready' | 'failed'

export interface StyleSampleSummary {
  id: number
  title: string
  author: string | null
  source: string | null
  genre: string | null
  tags: string | null
  total_chars: number
  index_status: IndexStatus
  index_error: string | null
  extracted_at: string | null
  created_at: string
  updated_at: string | null
}

export interface StyleGuideStructured {
  pov?: string
  tense?: string
  sentence_length?: string
  dialogue_density?: string
  pacing?: string
  opening_formula?: string
  ending_formula?: string
  signature_devices?: string[]
}

export interface StyleGuide {
  structured: StyleGuideStructured
  prose_excerpt: string
  prompt_fragment: string
}

export interface StyleSampleDetail extends StyleSampleSummary {
  file_path: string | null
  file_format: string | null
  notes: string | null
  content: string
  extraction_model: string | null
  style_guide: StyleGuide | null
}

export interface SearchHitChunk {
  chunk_index: number
  content: string
  char_count: number
  similarity: number
}

export interface SearchHit {
  sample: StyleSampleSummary
  top_chunks: SearchHitChunk[]
  style_guide: StyleGuide | null
}

export async function listStyleSamples(params?: { genre?: string }): Promise<StyleSampleSummary[]> {
  const qs = params?.genre ? `?genre=${encodeURIComponent(params.genre)}` : ''
  return request.get<StyleSampleSummary[]>(`/style-samples${qs}`)
}

export async function getStyleSample(id: number): Promise<StyleSampleDetail> {
  return request.get<StyleSampleDetail>(`/style-samples/${id}`)
}

export async function uploadStyleSample(
  file: File,
  meta: { title: string; author?: string; source?: string; genre?: string; tags?: string; notes?: string }
): Promise<StyleSampleSummary> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('title', meta.title)
  if (meta.author) fd.append('author', meta.author)
  if (meta.source) fd.append('source', meta.source)
  if (meta.genre) fd.append('genre', meta.genre)
  if (meta.tags) fd.append('tags', meta.tags)
  if (meta.notes) fd.append('notes', meta.notes)
  return request.post<StyleSampleSummary>('/style-samples', fd)
}

export async function deleteStyleSample(id: number): Promise<void> {
  return request.delete<void>(`/style-samples/${id}`)
}

export async function reindexStyleSample(id: number): Promise<StyleSampleSummary> {
  return request.post<StyleSampleSummary>(`/style-samples/${id}/reindex`, {})
}

export async function searchStyleSamples(payload: {
  query: string
  top_k?: number
  filter?: Record<string, unknown>
}): Promise<SearchHit[]> {
  return request.post<SearchHit[]>('/style-samples/search', {
    top_k: 5,
    filter: {},
    ...payload,
  })
}
