import request, { authedFetch } from './request'

export interface ReferenceNovel {
  id: number
  title: string
  author: string | null
  genre: string | null
  source: string | null
  tags: string | null
  reference_type: string | null
  file_path: string | null
  file_format: string | null
  total_chars: number
  chapter_count: number
  avg_chapter_length: number
  summary: string | null
  writing_style: string | null
  rating: number | null
  notes: string | null
  created_at: string
  updated_at: string | null
}

// 参考小说详情（包含分析和内容）
export interface ReferenceNovelDetail extends ReferenceNovel {
  analysis: string | null
  content: string | null
  chapters_data: Record<string, unknown> | null
}

export interface ReferenceStats {
  total_count: number
  genre_distribution: Record<string, number>
  avg_length: number
  total_chars: number
  type_distribution: Record<string, number>
}

export async function getReferences(params?: {
  genre?: string
  reference_type?: string
  search?: string
}): Promise<ReferenceNovel[]> {
  const query = new URLSearchParams()
  if (params?.genre) query.set('genre', params.genre)
  if (params?.reference_type) query.set('reference_type', params.reference_type)
  if (params?.search) query.set('search', params.search)
  const qs = query.toString()
  return request.get<ReferenceNovel[]>(`/references/${qs ? '?' + qs : ''}`)
}

export async function getReference(id: number): Promise<ReferenceNovelDetail> {
  return request.get<ReferenceNovelDetail>(`/references/${id}`)
}

export async function getReferenceStats(): Promise<ReferenceStats> {
  return request.get<ReferenceStats>('/references/stats')
}

export async function getReferenceAnalysis(id: number): Promise<Record<string, unknown>> {
  return request.get<Record<string, unknown>>(`/references/${id}/analysis`)
}

export async function getReferenceChapters(id: number): Promise<Array<Record<string, unknown>>> {
  return request.get<Array<Record<string, unknown>>>(`/references/${id}/chapters`)
}

export async function uploadReference(file: File, metadata?: {
  title?: string
  author?: string
  genre?: string
  reference_type?: string
  tags?: string
  notes?: string
  rating?: number
}): Promise<ReferenceNovel> {
  const formData = new FormData()
  formData.append('file', file)
  if (metadata?.title) formData.append('title', metadata.title)
  if (metadata?.author) formData.append('author', metadata.author)
  if (metadata?.genre) formData.append('genre', metadata.genre)
  if (metadata?.reference_type) formData.append('reference_type', metadata.reference_type)
  if (metadata?.tags) formData.append('tags', metadata.tags)
  if (metadata?.notes) formData.append('notes', metadata.notes)
  if (metadata?.rating) formData.append('rating', String(metadata.rating))

  const resp = await authedFetch('/api/v1/references/upload', {
    method: 'POST',
    body: formData,
  })
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: '上传失败' }))
    throw new Error(err.detail || '上传失败')
  }
  return resp.json()
}

export async function updateReference(id: number, data: Partial<ReferenceNovel>): Promise<ReferenceNovel> {
  return request.put<ReferenceNovel>(`/references/${id}`, data)
}

export async function deleteReference(id: number): Promise<void> {
  return request.delete(`/references/${id}`)
}
