import request from './request'

// 章节数据类型
export interface Chapter {
  id: number
  project_id: number
  title: string
  content: string
  word_count: number
  sort_order: number
  created_at: string
  updated_at: string
}

export interface CreateChapterData {
  title: string
  content?: string
  sort_order?: number
}

export interface UpdateChapterData {
  title?: string
  content?: string
  sort_order?: number
}

export interface ChapterOrder {
  id: number
  sort_order: number
}

// 获取项目的所有章节
export function getChapters(projectId: number) {
  return request.get<Chapter[]>(`/projects/${projectId}/chapters`) as Promise<Chapter[]>
}

// 创建章节
export function createChapter(projectId: number, data: CreateChapterData) {
  return request.post<Chapter>(`/projects/${projectId}/chapters`, data) as Promise<Chapter>
}

// 获取单个章节
export function getChapter(projectId: number, chapterId: number) {
  return request.get<Chapter>(
    `/projects/${projectId}/chapters/${chapterId}`
  ) as Promise<Chapter>
}

// 更新章节
export function updateChapter(projectId: number, chapterId: number, data: UpdateChapterData) {
  return request.put<Chapter>(
    `/projects/${projectId}/chapters/${chapterId}`,
    data
  ) as Promise<Chapter>
}

// 删除章节
export function deleteChapter(projectId: number, chapterId: number) {
  return request.delete(`/projects/${projectId}/chapters/${chapterId}`) as Promise<void>
}

// 重新排序章节
export function reorderChapters(projectId: number, orders: ChapterOrder[]) {
  return request.post(`/projects/${projectId}/chapters/reorder`, { orders }) as Promise<void>
}
