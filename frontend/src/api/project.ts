import request from './request'

// 项目数据类型
export interface Project {
  id: number
  title: string
  description: string
  genre: string
  target_word_count: number
  current_word_count: number
  status: 'planning' | 'writing' | 'completed' | 'archived'
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
  status?: string
}

// 获取项目列表
export function getProjects(status?: string) {
  return request.get<Project[]>('/projects', {
    params: status ? { status } : undefined,
  }) as Promise<Project[]>
}

// 创建项目
export function createProject(data: CreateProjectData) {
  return request.post<Project>('/projects', data) as Promise<Project>
}

// 获取单个项目
export function getProject(id: number) {
  return request.get<Project>(`/projects/${id}`) as Promise<Project>
}

// 更新项目
export function updateProject(id: number, data: UpdateProjectData) {
  return request.put<Project>(`/projects/${id}`, data) as Promise<Project>
}

// 删除项目
export function deleteProject(id: number) {
  return request.delete(`/projects/${id}`) as Promise<void>
}
