/**
 * 扩写模块 Pinia Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getExpansionProjects,
  createExpansionProject,
  uploadExpansionProject,
  importFromNovel,
  importFromDrama,
  getExpansionProject,
  updateExpansionProject,
  deleteExpansionProject,
  streamAnalyzeProject,
  streamResegmentProject,
  streamResegmentSegments,
  getSegments,
  updateSegment,
  splitSegment,
  mergeSegments,
  reorderSegments,
  streamExpandProject,
  streamExpandSegment,
  pauseExpansion,
  streamResumeExpansion,
  streamRetrySegment,
  getExportUrl,
  convertProject,
} from '@/api/expansion'
import type {
  ExpansionProject,
  ExpansionProjectListItem,
  ExpansionSegment,
  CreateExpansionProjectData,
  UpdateExpansionProjectData,
  UpdateSegmentData,
  SegmentSplitData,
  SegmentMergeData,
  ImportFromNovelData,
  ImportFromDramaData,
  StreamCallbacks,
  ProjectStatus,
} from '@/api/expansion'

export const useExpansionStore = defineStore('expansion', () => {
  // State
  const projects = ref<ExpansionProjectListItem[]>([])
  const currentProject = ref<ExpansionProject | null>(null)
  const segments = ref<ExpansionSegment[]>([])
  const currentSegmentId = ref<number | null>(null)
  const isAnalyzing = ref(false)
  const isExpanding = ref(false)
  const expandingSegmentId = ref<number | null>(null)
  const loading = ref(false)

  // ── Project Actions ──

  async function fetchProjects(params?: { status?: string; expansion_level?: string; page?: number; page_size?: number }) {
    loading.value = true
    try {
      projects.value = await getExpansionProjects(params)
    } finally {
      loading.value = false
    }
  }

  async function createProject(data: CreateExpansionProjectData) {
    const project = await createExpansionProject(data)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      source_type: project.source_type,
      word_count: project.word_count,
      expansion_level: project.expansion_level,
      status: project.status,
      created_at: project.created_at,
    })
    return project
  }

  async function uploadProject(file: File, title?: string, expansionLevel?: 'light' | 'medium' | 'deep', targetWordCount?: number, styleInstructions?: string, executionMode?: 'auto' | 'step_by_step') {
    const project = await uploadExpansionProject(file, title, expansionLevel, targetWordCount, styleInstructions, executionMode)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      source_type: project.source_type,
      word_count: project.word_count,
      expansion_level: project.expansion_level,
      status: project.status,
      created_at: project.created_at,
    })
    return project
  }

  async function importFromNovelProject(data: ImportFromNovelData) {
    const project = await importFromNovel(data)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      source_type: project.source_type,
      word_count: project.word_count,
      expansion_level: project.expansion_level,
      status: project.status,
      created_at: project.created_at,
    })
    return project
  }

  async function importFromDramaProject(data: ImportFromDramaData) {
    const project = await importFromDrama(data)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      source_type: project.source_type,
      word_count: project.word_count,
      expansion_level: project.expansion_level,
      status: project.status,
      created_at: project.created_at,
    })
    return project
  }

  async function fetchProject(id: number) {
    loading.value = true
    try {
      currentProject.value = await getExpansionProject(id)
    } finally {
      loading.value = false
    }
  }

  async function updateProject(id: number, data: UpdateExpansionProjectData) {
    const updated = await updateExpansionProject(id, data)
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  async function removeProject(id: number) {
    await deleteExpansionProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) {
      currentProject.value = null
      segments.value = []
    }
  }

  // ── Analysis (SSE) ──

  function startAnalysis(id: number, callbacks?: { onText?: (text: string) => void; onEvent?: (type: string, data: unknown) => void; onDone?: () => void; onError?: (error: string) => void }): AbortController {
    isAnalyzing.value = true

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onEvent: (type, data) => {
        // Handle specific events like status changes
        if (type === 'status' && currentProject.value) {
          const newStatus = (data as { status?: string })?.status
          if (newStatus) {
            currentProject.value.status = newStatus as ProjectStatus
          }
        }
        // Forward phase events to caller
        callbacks?.onEvent?.(type, data)
      },
      onDone: () => {
        isAnalyzing.value = false
        callbacks?.onDone?.()
        // Refresh project and segments after analysis
        fetchProject(id)
        fetchSegments(id)
      },
      onError: (error) => {
        isAnalyzing.value = false
        callbacks?.onError?.(error)
      },
    }

    return streamAnalyzeProject(id, streamCallbacks)
  }

  function resegment(id: number, callbacks?: { onText?: (text: string) => void; onEvent?: (type: string, data: unknown) => void; onDone?: () => void; onError?: (error: string) => void }): AbortController {
    isAnalyzing.value = true

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onEvent: (type, data) => {
        callbacks?.onEvent?.(type, data)
      },
      onDone: () => {
        isAnalyzing.value = false
        callbacks?.onDone?.()
        // Refresh project and segments after resegment
        fetchProject(id)
        fetchSegments(id)
      },
      onError: (error) => {
        isAnalyzing.value = false
        callbacks?.onError?.(error)
      },
    }

    return streamResegmentProject(id, streamCallbacks)
  }

  function resegmentSegments(id: number, segmentIds: number[], callbacks?: { onText?: (text: string) => void; onEvent?: (type: string, data: unknown) => void; onDone?: () => void; onError?: (error: string) => void }): AbortController {
    return streamResegmentSegments(id, segmentIds, {
      onText: (text) => callbacks?.onText?.(text),
      onEvent: (type, data) => callbacks?.onEvent?.(type, data),
      onDone: () => callbacks?.onDone?.(),
      onError: (error) => callbacks?.onError?.(error),
    })
  }

  // ── Segment Actions ──

  async function fetchSegments(projectId: number) {
    segments.value = await getSegments(projectId)
  }

  async function editSegment(projectId: number, segId: number, data: UpdateSegmentData) {
    const updated = await updateSegment(projectId, segId, data)
    const idx = segments.value.findIndex((s) => s.id === segId)
    if (idx !== -1) {
      segments.value[idx] = updated
    }
    return updated
  }

  async function splitSegmentAction(projectId: number, data: SegmentSplitData) {
    const updatedSegments = await splitSegment(projectId, data)
    segments.value = updatedSegments
    return updatedSegments
  }

  async function mergeSegmentsAction(projectId: number, data: SegmentMergeData) {
    const mergedSegment = await mergeSegments(projectId, data)
    // Refresh segments after merge
    await fetchSegments(projectId)
    return mergedSegment
  }

  async function reorderSegmentsAction(projectId: number, order: number[]) {
    await reorderSegments(projectId, order)
    await fetchSegments(projectId)
  }

  // ── Expansion (SSE) ──

  function expandProject(id: number, callbacks?: { onText?: (text: string) => void; onEvent?: (type: string, data: unknown) => void; onDone?: () => void; onError?: (error: string, segmentId?: number) => void }): AbortController {
    isExpanding.value = true

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onEvent: (type, data) => {
        callbacks?.onEvent?.(type, data)
        // Handle segment status updates
        if (type === 'segment_start' && data) {
          expandingSegmentId.value = (data as { segment_id?: number })?.segment_id || null
        }
        if (type === 'segment_done' && data) {
          const segId = (data as { segment_id?: number })?.segment_id
          if (segId) {
            const idx = segments.value.findIndex((s) => s.id === segId)
            if (idx !== -1) {
              segments.value[idx].status = 'completed'
            }
          }
        }
        if (type === 'status' && currentProject.value) {
          const newStatus = (data as { status?: string })?.status
          if (newStatus) {
            currentProject.value.status = newStatus as ProjectStatus
          }
        }
      },
      onDone: () => {
        isExpanding.value = false
        expandingSegmentId.value = null
        callbacks?.onDone?.()
        // Refresh data after expansion
        fetchProject(id)
        fetchSegments(id)
      },
      onError: (error) => {
        isExpanding.value = false
        expandingSegmentId.value = null
        callbacks?.onError?.(error)
      },
    }

    return streamExpandProject(id, streamCallbacks)
  }

  function expandSegment(projectId: number, segId: number, data?: { expansion_level?: 'light' | 'medium' | 'deep'; custom_instructions?: string }, callbacks?: { onText?: (text: string) => void; onDone?: () => void; onError?: (error: string) => void }): AbortController {
    expandingSegmentId.value = segId

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onDone: () => {
        expandingSegmentId.value = null
        callbacks?.onDone?.()
        // Refresh segments after expansion
        fetchSegments(projectId)
      },
      onError: (error) => {
        expandingSegmentId.value = null
        callbacks?.onError?.(error)
      },
    }

    return streamExpandSegment(projectId, segId, streamCallbacks, data)
  }

  async function pauseExpansionAction(id: number) {
    await pauseExpansion(id)
    isExpanding.value = false
    expandingSegmentId.value = null
    if (currentProject.value?.id === id) {
      currentProject.value.status = 'paused'
    }
  }

  function resumeExpansion(id: number, callbacks?: { onText?: (text: string) => void; onEvent?: (type: string, data: unknown) => void; onDone?: () => void; onError?: (error: string, segmentId?: number) => void }): AbortController {
    isExpanding.value = true

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onEvent: (type, data) => {
        callbacks?.onEvent?.(type, data)
        if (type === 'segment_start' && data) {
          expandingSegmentId.value = (data as { segment_id?: number })?.segment_id || null
        }
        if (type === 'segment_done' && data) {
          const segId = (data as { segment_id?: number })?.segment_id
          if (segId) {
            const idx = segments.value.findIndex((s) => s.id === segId)
            if (idx !== -1) {
              segments.value[idx].status = 'completed'
            }
          }
        }
        if (type === 'status' && currentProject.value) {
          const newStatus = (data as { status?: string })?.status
          if (newStatus) {
            currentProject.value.status = newStatus as ProjectStatus
          }
        }
      },
      onDone: () => {
        isExpanding.value = false
        expandingSegmentId.value = null
        callbacks?.onDone?.()
        fetchProject(id)
        fetchSegments(id)
      },
      onError: (error) => {
        isExpanding.value = false
        expandingSegmentId.value = null
        callbacks?.onError?.(error)
      },
    }

    return streamResumeExpansion(id, streamCallbacks)
  }

  function retrySegment(projectId: number, segId: number, callbacks?: { onText?: (text: string) => void; onDone?: () => void; onError?: (error: string) => void }): AbortController {
    expandingSegmentId.value = segId

    // Mark segment as expanding
    const idx = segments.value.findIndex((s) => s.id === segId)
    if (idx !== -1) {
      segments.value[idx].status = 'expanding'
      segments.value[idx].error_message = null
    }

    const streamCallbacks: StreamCallbacks = {
      onText: (text) => {
        callbacks?.onText?.(text)
      },
      onDone: () => {
        expandingSegmentId.value = null
        callbacks?.onDone?.()
        fetchSegments(projectId)
      },
      onError: (error) => {
        expandingSegmentId.value = null
        const segIdx = segments.value.findIndex((s) => s.id === segId)
        if (segIdx !== -1) {
          segments.value[segIdx].status = 'error'
          segments.value[segIdx].error_message = error
        }
        callbacks?.onError?.(error)
      },
    }

    return streamRetrySegment(projectId, segId, streamCallbacks)
  }

  // ── Export & Convert ──

  function exportProject(id: number, format: 'txt' | 'md' | 'docx', version: 'original' | 'expanded' | 'both') {
    const url = getExportUrl(id, format, version)
    window.open(url, '_blank')
  }

  async function convertProjectAction(id: number, target: 'novel' | 'drama') {
    const result = await convertProject(id, { target })
    return result
  }

  // ── UI Helpers ──

  function setCurrentSegment(id: number | null) {
    currentSegmentId.value = id
  }

  function clearCurrentProject() {
    currentProject.value = null
    segments.value = []
    currentSegmentId.value = null
    isAnalyzing.value = false
    isExpanding.value = false
    expandingSegmentId.value = null
  }

  return {
    // State
    projects,
    currentProject,
    segments,
    currentSegmentId,
    isAnalyzing,
    isExpanding,
    expandingSegmentId,
    loading,

    // Project Actions
    fetchProjects,
    createProject,
    uploadProject,
    importFromNovelProject,
    importFromDramaProject,
    fetchProject,
    updateProject,
    removeProject,

    // Analysis
    startAnalysis,
    resegment,
    resegmentSegments,

    // Segment Actions
    fetchSegments,
    editSegment,
    splitSegmentAction,
    mergeSegmentsAction,
    reorderSegmentsAction,

    // Expansion Actions
    expandProject,
    expandSegment,
    pauseExpansionAction,
    resumeExpansion,
    retrySegment,

    // Export & Convert
    exportProject,
    convertProjectAction,

    // UI Helpers
    setCurrentSegment,
    clearCurrentProject,
  }
})