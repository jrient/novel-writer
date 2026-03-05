import request from './request'

// 角色数据类型
export interface Character {
  id: number
  project_id: number
  name: string
  role_type: string
  avatar_url: string | null
  age: string | null
  gender: string | null
  occupation: string | null
  personality_traits: string | null
  appearance: string | null
  background: string | null
  relationships: string | null
  growth_arc: string | null
  tags: string | null
  notes: string | null
  created_at: string
  updated_at: string | null
}

export interface CreateCharacterData {
  name: string
  role_type?: string
  avatar_url?: string
  age?: string
  gender?: string
  occupation?: string
  personality_traits?: string
  appearance?: string
  background?: string
  relationships?: string
  growth_arc?: string
  tags?: string
  notes?: string
}

export interface UpdateCharacterData {
  name?: string
  role_type?: string
  avatar_url?: string
  age?: string
  gender?: string
  occupation?: string
  personality_traits?: string
  appearance?: string
  background?: string
  relationships?: string
  growth_arc?: string
  tags?: string
  notes?: string
}

// 获取角色列表
export async function getCharacters(projectId: number, roleType?: string): Promise<Character[]> {
  const params = roleType ? { role_type: roleType } : {}
  return request.get<Character[]>(`/projects/${projectId}/characters/`, { params })
}

// 创建角色
export async function createCharacter(projectId: number, data: CreateCharacterData): Promise<Character> {
  return request.post<Character>(`/projects/${projectId}/characters/`, data)
}

// 获取单个角色
export async function getCharacter(projectId: number, characterId: number): Promise<Character> {
  return request.get<Character>(`/projects/${projectId}/characters/${characterId}/`)
}

// 更新角色
export async function updateCharacter(
  projectId: number,
  characterId: number,
  data: UpdateCharacterData
): Promise<Character> {
  return request.put<Character>(`/projects/${projectId}/characters/${characterId}/`, data)
}

// 删除角色
export async function deleteCharacter(projectId: number, characterId: number): Promise<void> {
  return request.delete(`/projects/${projectId}/characters/${characterId}/`)
}