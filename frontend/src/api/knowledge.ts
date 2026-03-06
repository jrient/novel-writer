import request from './request'

export interface KnowledgeEntry {
  id: number
  keyword: string
  title: string
  content: string
  source_url?: string
  category?: string
  usage_count: number
  created_at: string
}

export const knowledgeApi = {
  search: (keyword: string, maxResults = 3) =>
    request.post<KnowledgeEntry[]>('/knowledge/search', { keyword, max_results: maxResults }),

  list: (keyword?: string) =>
    request.get<KnowledgeEntry[]>('/knowledge/', { params: { keyword } }),

  delete: (id: number) =>
    request.delete(`/knowledge/${id}`),
}
