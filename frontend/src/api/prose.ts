import request from './request'

export interface ProseSceneOut {
  id: number
  scene_index: number
  scene_title: string
  original_scene_text: string
  prose_text: string | null
  status: string
  error: string | null
  token_used: number
}

export interface ProseProjectOut {
  id: number
  user_id: number
  title: string
  script_project_id: number | null
  script_project_title: string | null
  premise: string
  genre: string | null
  style_snapshot: string | null
  status: string
  total_scenes: number
  done_scenes: number
  failed_scenes: number
  created_at: string
  updated_at: string | null
}

export interface ProseProjectDetail extends ProseProjectOut {
  scenes: ProseSceneOut[]
}

export interface ProseCreateForm {
  file: File
  premise: string
  title?: string
  genre?: string
}

export const proseApi = {
  create(form: ProseCreateForm) {
    const fd = new FormData()
    fd.append('file', form.file)
    fd.append('premise', form.premise)
    if (form.title) fd.append('title', form.title)
    if (form.genre) fd.append('genre', form.genre)
    return request.post<ProseProjectOut>('/prose', fd, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },

  list() {
    return request.get<ProseProjectOut[]>('/prose')
  },

  get(id: number) {
    return request.get<ProseProjectDetail>(`/prose/${id}`)
  },

  delete(id: number) {
    return request.delete(`/prose/${id}`)
  },

  getStreamTicket(id: number) {
    return request.post<{ ticket: string }>(`/prose/${id}/stream/ticket`)
  },

  getStreamUrl(id: number, ticket: string): string {
    const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    return `${base}/api/v1/prose/${id}/stream?ticket=${ticket}`
  },
}
