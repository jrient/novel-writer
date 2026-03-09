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
export async function getChapters(projectId: number): Promise<Chapter[]> {
  return request.get<Chapter[]>(`/projects/${projectId}/chapters/`)
}

// 创建章节
export async function createChapter(projectId: number, data: CreateChapterData): Promise<Chapter> {
  return request.post<Chapter>(`/projects/${projectId}/chapters/`, data)
}

// 获取单个章节
export async function getChapter(projectId: number, chapterId: number): Promise<Chapter> {
  return request.get<Chapter>(`/projects/${projectId}/chapters/${chapterId}/`)
}

// 更新章节
export async function updateChapter(
  projectId: number,
  chapterId: number,
  data: UpdateChapterData
): Promise<Chapter> {
  return request.put<Chapter>(`/projects/${projectId}/chapters/${chapterId}/`, data)
}

// 删除章节
export async function deleteChapter(projectId: number, chapterId: number): Promise<void> {
  return request.delete(`/projects/${projectId}/chapters/${chapterId}/`)
}

// 批量删除章节
export async function batchDeleteChapters(projectId: number, chapterIds: number[]): Promise<void> {
  return request.post(`/projects/${projectId}/chapters/batch-delete/`, { ids: chapterIds })
}

// 重新排序章节
export async function reorderChapters(projectId: number, orders: ChapterOrder[]): Promise<void> {
  return request.post(`/projects/${projectId}/chapters/reorder/`, { orders })
}