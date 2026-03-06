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
  search: (keyword: string, maxResults = 3, useAI = false) =>
    request.post<KnowledgeEntry[]>('/knowledge/search', {
      keywords: [keyword],
      max_results_per_keyword: maxResults,
      use_ai: useAI
    }),

  list: (keyword?: string) =>
    request.get<KnowledgeEntry[]>('/knowledge/', { params: { keyword } }),

  delete: (id: number) =>
    request.delete(`/knowledge/${id}`),
}
