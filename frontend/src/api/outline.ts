import request from './request'

// 大纲节点数据类型
export interface OutlineNode {
  id: number
  project_id: number
  node_type: string
  title: string
  content: string | null
  parent_id: number | null
  level: number
  sort_order: number
  chapter_id: number | null
  pov_character_id: number | null
  status: string
  estimated_words: number | null
  notes: string | null
  created_at: string
  updated_at: string | null
  children?: OutlineNode[]
}

export interface CreateOutlineNodeData {
  node_type?: string
  title: string
  content?: string
  parent_id?: number
  level?: number
  sort_order?: number
  chapter_id?: number
  pov_character_id?: number
  status?: string
  estimated_words?: number
  notes?: string
}

export interface UpdateOutlineNodeData {
  node_type?: string
  title?: string
  content?: string
  parent_id?: number
  level?: number
  sort_order?: number
  chapter_id?: number
  pov_character_id?: number
  status?: string
  estimated_words?: number
  notes?: string
}

// 获取大纲节点列表
export async function getOutlineNodes(projectId: number, nodeType?: string): Promise<OutlineNode[]> {
  const params = nodeType ? { node_type: nodeType } : {}
  return request.get<OutlineNode[]>(`/projects/${projectId}/outline/`, { params })
}

// 获取大纲树
export async function getOutlineTree(projectId: number): Promise<OutlineNode[]> {
  return request.get<OutlineNode[]>(`/projects/${projectId}/outline/tree/`)
}

// 创建大纲节点
export async function createOutlineNode(projectId: number, data: CreateOutlineNodeData): Promise<OutlineNode> {
  return request.post<OutlineNode>(`/projects/${projectId}/outline/`, data)
}

// 获取单个节点
export async function getOutlineNode(projectId: number, nodeId: number): Promise<OutlineNode> {
  return request.get<OutlineNode>(`/projects/${projectId}/outline/${nodeId}/`)
}

// 更新大纲节点
export async function updateOutlineNode(
  projectId: number,
  nodeId: number,
  data: UpdateOutlineNodeData
): Promise<OutlineNode> {
  return request.put<OutlineNode>(`/projects/${projectId}/outline/${nodeId}/`, data)
}

// 删除大纲节点
export async function deleteOutlineNode(projectId: number, nodeId: number): Promise<void> {
  return request.delete(`/projects/${projectId}/outline/${nodeId}/`)
}

// 重新排序大纲节点
export async function reorderOutlineNodes(projectId: number, orders: { id: number; sort_order: number; parent_id?: number }[]): Promise<void> {
  return request.post(`/projects/${projectId}/outline/reorder/`, { orders })
}