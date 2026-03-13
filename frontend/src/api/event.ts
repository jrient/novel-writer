import request from './request'

// ============ 类型定义 ============

export interface Plotline {
  id: number
  project_id: number
  name: string
  description: string | null
  color: string
  sort_order: number
  created_at: string
  updated_at: string | null
}

export interface CreatePlotlineData {
  name: string
  description?: string
  color?: string
  sort_order?: number
}

export interface UpdatePlotlineData {
  name?: string
  description?: string
  color?: string
  sort_order?: number
}

export interface StoryEvent {
  id: number
  project_id: number
  title: string
  description: string | null
  event_type: string
  status: string
  anchor_type: string | null
  anchor_id: string | null
  plotline_ids: number[]
  timeline_order: number
  time_label: string | null
  character_ids: number[]
  location_map_id: string | null
  cause_event_ids: number[]
  effect_event_ids: number[]
  foreshadow_event_id: number | null
  tags: string[]
  importance: string
  sort_order: number
  created_at: string
  updated_at: string | null
}

export interface CreateEventData {
  title: string
  description?: string
  event_type?: string
  status?: string
  anchor_type?: string
  anchor_id?: string
  plotline_ids?: number[]
  timeline_order?: number
  time_label?: string
  character_ids?: number[]
  location_map_id?: string
  cause_event_ids?: number[]
  effect_event_ids?: number[]
  foreshadow_event_id?: number
  tags?: string[]
  importance?: string
  sort_order?: number
}

export interface UpdateEventData {
  title?: string
  description?: string
  event_type?: string
  status?: string
  anchor_type?: string
  anchor_id?: string
  plotline_ids?: number[]
  timeline_order?: number
  time_label?: string
  character_ids?: number[]
  location_map_id?: string
  cause_event_ids?: number[]
  effect_event_ids?: number[]
  foreshadow_event_id?: number
  tags?: string[]
  importance?: string
  sort_order?: number
}

export interface EventChain {
  current: StoryEvent
  causes: StoryEvent[]
  effects: StoryEvent[]
}

export interface EventFilters {
  plotline_id?: number
  event_type?: string
  anchor_type?: string
  status?: string
}

// ============ Plotline API ============

export async function getPlotlines(projectId: number): Promise<Plotline[]> {
  return request.get<Plotline[]>(`/projects/${projectId}/events/plotlines/`)
}

export async function createPlotline(projectId: number, data: CreatePlotlineData): Promise<Plotline> {
  return request.post<Plotline>(`/projects/${projectId}/events/plotlines/`, data)
}

export async function updatePlotline(projectId: number, id: number, data: UpdatePlotlineData): Promise<Plotline> {
  return request.put<Plotline>(`/projects/${projectId}/events/plotlines/${id}`, data)
}

export async function deletePlotline(projectId: number, id: number): Promise<void> {
  return request.delete(`/projects/${projectId}/events/plotlines/${id}`)
}

// ============ Event API ============

export async function getEvents(projectId: number, filters?: EventFilters): Promise<StoryEvent[]> {
  return request.get<StoryEvent[]>(`/projects/${projectId}/events/`, {
    params: filters,
  })
}

export async function createEvent(projectId: number, data: CreateEventData): Promise<StoryEvent> {
  return request.post<StoryEvent>(`/projects/${projectId}/events/`, data)
}

export async function getEvent(projectId: number, id: number): Promise<StoryEvent> {
  return request.get<StoryEvent>(`/projects/${projectId}/events/${id}`)
}

export async function updateEvent(projectId: number, id: number, data: UpdateEventData): Promise<StoryEvent> {
  return request.put<StoryEvent>(`/projects/${projectId}/events/${id}`, data)
}

export async function deleteEvent(projectId: number, id: number): Promise<void> {
  return request.delete(`/projects/${projectId}/events/${id}`)
}

export async function getEventChain(projectId: number, id: number): Promise<EventChain> {
  return request.get<EventChain>(`/projects/${projectId}/events/${id}/chain`)
}
