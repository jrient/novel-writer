/**
 * 剧本模块 Pinia Store
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getDramaProjects,
  createDramaProject,
  getDramaProject,
  updateDramaProject,
  deleteDramaProject,
  updateAIConfig,
  getNodes,
  createNode,
  updateNode,
  deleteNode,
  reorderNodes,
  getOrCreateSession,
  deleteSession,
  confirmOutline,
} from '@/api/drama'
import type {
  ScriptProject,
  ScriptProjectListItem,
  CreateScriptProjectData,
  UpdateScriptProjectData,
  ScriptNode,
  CreateNodeData,
  UpdateNodeData,
  ReorderItem,
  ScriptSession,
  AIConfig,
} from '@/api/drama'

export const useDramaStore = defineStore('drama', () => {
  // State
  const projects = ref<ScriptProjectListItem[]>([])
  const currentProject = ref<ScriptProject | null>(null)
  const nodes = ref<ScriptNode[]>([])
  const currentNode = ref<ScriptNode | null>(null)
  const session = ref<ScriptSession | null>(null)
  const loading = ref(false)

  // ── Project Actions ──

  async function fetchProjects(params?: { script_type?: string; status?: string }) {
    loading.value = true
    try {
      projects.value = await getDramaProjects(params)
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: number) {
    loading.value = true
    try {
      currentProject.value = await getDramaProject(id)
    } finally {
      loading.value = false
    }
  }

  async function createProject(data: CreateScriptProjectData) {
    const project = await createDramaProject(data)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      script_type: project.script_type,
      concept: project.concept,
      status: project.status,
      created_at: project.created_at,
      updated_at: project.updated_at,
    })
    return project
  }

  async function updateProject(id: number, data: UpdateScriptProjectData) {
    const updated = await updateDramaProject(id, data)
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  async function removeProject(id: number) {
    await deleteDramaProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) {
      currentProject.value = null
    }
  }

  async function updateProjectAIConfig(id: number, config: AIConfig) {
    const updated = await updateAIConfig(id, config)
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  // ── Node Actions ──

  async function fetchNodes(projectId: number) {
    nodes.value = await getNodes(projectId)
  }

  async function addNode(projectId: number, data: CreateNodeData) {
    const node = await createNode(projectId, data)
    await fetchNodes(projectId)
    return node
  }

  async function editNode(projectId: number, nodeId: number, data: UpdateNodeData) {
    const updated = await updateNode(projectId, nodeId, data)
    if (currentNode.value?.id === nodeId) {
      currentNode.value = updated
    }
    await fetchNodes(projectId)
    return updated
  }

  async function removeNode(projectId: number, nodeId: number) {
    await deleteNode(projectId, nodeId)
    if (currentNode.value?.id === nodeId) {
      currentNode.value = null
    }
    await fetchNodes(projectId)
  }

  async function reorder(projectId: number, orders: ReorderItem[]) {
    await reorderNodes(projectId, orders)
    await fetchNodes(projectId)
  }

  function selectNode(node: ScriptNode | null) {
    currentNode.value = node
  }

  // ── Session Actions ──

  async function fetchSession(projectId: number) {
    session.value = await getOrCreateSession(projectId)
  }

  async function resetSession(projectId: number) {
    await deleteSession(projectId)
    session.value = null
  }

  async function confirmProjectOutline(projectId: number) {
    await confirmOutline(projectId)
    session.value = null
    await fetchNodes(projectId)
  }

  return {
    projects,
    currentProject,
    nodes,
    currentNode,
    session,
    loading,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    removeProject,
    updateProjectAIConfig,
    fetchNodes,
    addNode,
    editNode,
    removeNode,
    reorder,
    selectNode,
    fetchSession,
    resetSession,
    confirmProjectOutline,
  }
})
