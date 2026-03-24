/**
 * 笔记/妙记 API
 */
import request from './request'

export interface Note {
  id: number
  project_id: number
  title: string
  content: string | null
  note_type: string
  status: string
  related_chapter_ids: number[] | null
  sort_order: number
  created_at: string
  updated_at: string | null
}

export interface CreateNoteData {
  title: string
  content?: string
  note_type?: string
  status?: string
}

export interface UpdateNoteData {
  title?: string
  content?: string
  note_type?: string
  status?: string
}

export interface MiaojiParseResult {
  characters: Array<{
    name: string
    role_type: string
    gender?: string
    age?: string
    occupation?: string
    personality_traits?: string
    appearance?: string
    background?: string
  }>
  worldbuilding: Array<{
    name: string
    category: string
    description?: string
  }>
  outline: Array<{
    title: string
    summary?: string
    sort_order?: number
  }>
  events: Array<{
    title: string
    description?: string
    event_type?: string
    importance?: number
  }>
  summary: string
}

// 获取笔记列表
export async function getNotes(projectId: number, noteType?: string): Promise<Note[]> {
  const params = noteType ? `?note_type=${noteType}` : ''
  return request.get<Note[]>(`/projects/${projectId}/notes/${params}`)
}

// 获取单个笔记
export async function getNote(projectId: number, noteId: number): Promise<Note> {
  return request.get<Note>(`/projects/${projectId}/notes/${noteId}/`)
}

// 创建笔记
export async function createNote(projectId: number, data: CreateNoteData): Promise<Note> {
  return request.post<Note>(`/projects/${projectId}/notes/`, data)
}

// 更新笔记
export async function updateNote(projectId: number, noteId: number, data: UpdateNoteData): Promise<Note> {
  return request.put<Note>(`/projects/${projectId}/notes/${noteId}/`, data)
}

// 删除笔记
export async function deleteNote(projectId: number, noteId: number): Promise<void> {
  return request.delete(`/projects/${projectId}/notes/${noteId}/`)
}

// 快速创建妙记
export async function quickMiaoji(projectId: number, content: string): Promise<Note> {
  return request.post<Note>(`/projects/${projectId}/notes/miaoji/quick`, { content })
}

// 解析妙记
export async function parseMiaoji(projectId: number, noteId: number): Promise<MiaojiParseResult> {
  return request.post<MiaojiParseResult>(`/projects/${projectId}/notes/${noteId}/parse/`)
}