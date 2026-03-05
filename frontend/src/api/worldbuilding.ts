import request from './request'

// 世界观设定数据类型
export interface WorldbuildingEntry {
  id: number
  project_id: number
  category: string
  title: string
  content: string | null
  trigger_keywords: string | null
  parent_id: number | null
  level: number
  sort_order: number
  icon: string | null
  color: string | null
  created_at: string
  updated_at: string | null
  children?: WorldbuildingEntry[]
}

export interface CreateWorldbuildingData {
  category?: string
  title: string
  content?: string
  trigger_keywords?: string
  parent_id?: number
  level?: number
  sort_order?: number
  icon?: string
  color?: string
}

export interface UpdateWorldbuildingData {
  category?: string
  title?: string
  content?: string
  trigger_keywords?: string
  parent_id?: number
  level?: number
  sort_order?: number
  icon?: string
  color?: string
}

// 获取世界观设定列表
export async function getWorldbuilding(projectId: number, category?: string): Promise<WorldbuildingEntry[]> {
  const params = category ? { category } : {}
  return request.get<WorldbuildingEntry[]>(`/projects/${projectId}/worldbuilding/`, { params })
}

// 获取世界观设定树
export async function getWorldbuildingTree(projectId: number): Promise<WorldbuildingEntry[]> {
  return request.get<WorldbuildingEntry[]>(`/projects/${projectId}/worldbuilding/tree/`)
}

// 创建世界观设定
export async function createWorldbuilding(projectId: number, data: CreateWorldbuildingData): Promise<WorldbuildingEntry> {
  return request.post<WorldbuildingEntry>(`/projects/${projectId}/worldbuilding/`, data)
}

// 获取单个设定
export async function getWorldbuildingEntry(projectId: number, entryId: number): Promise<WorldbuildingEntry> {
  return request.get<WorldbuildingEntry>(`/projects/${projectId}/worldbuilding/${entryId}/`)
}

// 更新世界观设定
export async function updateWorldbuilding(
  projectId: number,
  entryId: number,
  data: UpdateWorldbuildingData
): Promise<WorldbuildingEntry> {
  return request.put<WorldbuildingEntry>(`/projects/${projectId}/worldbuilding/${entryId}/`, data)
}

// 删除世界观设定
export async function deleteWorldbuilding(projectId: number, entryId: number): Promise<void> {
  return request.delete(`/projects/${projectId}/worldbuilding/${entryId}/`)
}