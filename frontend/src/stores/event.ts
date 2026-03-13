import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  getPlotlines, createPlotline, updatePlotline as apiUpdatePlotline, deletePlotline,
  getEvents, createEvent, updateEvent as apiUpdateEvent, deleteEvent, getEventChain,
} from '@/api/event'
import type {
  Plotline, CreatePlotlineData, UpdatePlotlineData,
  StoryEvent, CreateEventData, UpdateEventData, EventChain, EventFilters,
} from '@/api/event'

export const useEventStore = defineStore('event', () => {
  // 状态
  const plotlines = ref<Plotline[]>([])
  const events = ref<StoryEvent[]>([])
  const currentEvent = ref<StoryEvent | null>(null)
  const currentChain = ref<EventChain | null>(null)
  const loading = ref(false)
  const plotlinesLoading = ref(false)

  // 筛选
  const filterPlotlineId = ref<number | null>(null)
  const filterEventType = ref<string>('')
  const filterStatus = ref<string>('')

  // 计算属性
  const filteredEvents = computed(() => {
    let result = events.value
    if (filterPlotlineId.value !== null) {
      result = result.filter(e => e.plotline_ids.includes(filterPlotlineId.value!))
    }
    if (filterEventType.value) {
      result = result.filter(e => e.event_type === filterEventType.value)
    }
    if (filterStatus.value) {
      result = result.filter(e => e.status === filterStatus.value)
    }
    return result
  })

  // Plotline 方法
  async function fetchPlotlines(projectId: number) {
    plotlinesLoading.value = true
    try {
      plotlines.value = await getPlotlines(projectId)
    } finally {
      plotlinesLoading.value = false
    }
  }

  async function createNewPlotline(projectId: number, data: CreatePlotlineData) {
    const plotline = await createPlotline(projectId, data)
    plotlines.value.push(plotline)
    return plotline
  }

  async function updatePlotline(projectId: number, id: number, data: UpdatePlotlineData) {
    const updated = await apiUpdatePlotline(projectId, id, data)
    const idx = plotlines.value.findIndex(p => p.id === id)
    if (idx !== -1) plotlines.value[idx] = updated
    return updated
  }

  async function removePlotline(projectId: number, id: number) {
    await deletePlotline(projectId, id)
    plotlines.value = plotlines.value.filter(p => p.id !== id)
  }

  // Event 方法
  async function fetchEvents(projectId: number, filters?: EventFilters) {
    loading.value = true
    try {
      events.value = await getEvents(projectId, filters)
    } finally {
      loading.value = false
    }
  }

  async function createNewEvent(projectId: number, data: CreateEventData) {
    const event = await createEvent(projectId, data)
    events.value.push(event)
    // 按 timeline_order 排序
    events.value.sort((a, b) => a.timeline_order - b.timeline_order)
    return event
  }

  async function updateEvent(projectId: number, id: number, data: UpdateEventData) {
    const updated = await apiUpdateEvent(projectId, id, data)
    const idx = events.value.findIndex(e => e.id === id)
    if (idx !== -1) events.value[idx] = updated
    if (currentEvent.value?.id === id) currentEvent.value = updated
    return updated
  }

  async function removeEvent(projectId: number, id: number) {
    await deleteEvent(projectId, id)
    events.value = events.value.filter(e => e.id !== id)
    if (currentEvent.value?.id === id) currentEvent.value = null
  }

  async function fetchEventChain(projectId: number, id: number) {
    currentChain.value = await getEventChain(projectId, id)
    return currentChain.value
  }

  function setCurrentEvent(event: StoryEvent | null) {
    currentEvent.value = event
  }

  function getPlotlineById(id: number) {
    return plotlines.value.find(p => p.id === id)
  }

  return {
    plotlines, events, currentEvent, currentChain, loading, plotlinesLoading,
    filterPlotlineId, filterEventType, filterStatus,
    filteredEvents,
    fetchPlotlines, createNewPlotline, updatePlotline, removePlotline,
    fetchEvents, createNewEvent, updateEvent, removeEvent,
    fetchEventChain, setCurrentEvent, getPlotlineById,
  }
})
