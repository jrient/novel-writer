import request from './request'

// 项目数据类型
export interface Project {
  id: number
  title: string
  description: string
  genre: string
  target_word_count: number
  current_word_count: number
  status: 'draft' | 'planning' | 'writing' | 'completed' | 'archived'
  created_at: string
  updated_at: string
}

export interface CreateProjectData {
  title: string
  description?: string
  genre?: string
  target_word_count?: number
}

export interface UpdateProjectData {
  title?: string
  description?: string
  genre?: string
  target_word_count?: number
  current_word_count?: number
  status?: string
}

// 获取项目列表
export async function getProjects(status?: string): Promise<Project[]> {
  return request.get<Project[]>('/projects/', {
    params: status ? { status } : undefined,
  })
}

// 创建项目
export async function createProject(data: CreateProjectData): Promise<Project> {
  return request.post<Project>('/projects/', data)
}

// 获取单个项目
export async function getProject(id: number): Promise<Project> {
  return request.get<Project>(`/projects/${id}/`)
}

// 更新项目
export async function updateProject(id: number, data: UpdateProjectData): Promise<Project> {
  return request.put<Project>(`/projects/${id}/`, data)
}

// 删除项目
export async function deleteProject(id: number): Promise<void> {
  return request.delete(`/projects/${id}/`)
}