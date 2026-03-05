import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getOutlineNodes,
  getOutlineTree,
  createOutlineNode,
  updateOutlineNode,
  deleteOutlineNode,
  reorderOutlineNodes,
} from '@/api/outline'
import type { OutlineNode, CreateOutlineNodeData, UpdateOutlineNodeData } from '@/api/outline'

export const useOutlineStore = defineStore('outline', () => {
  const nodes = ref<OutlineNode[]>([])
  const treeData = ref<OutlineNode[]>([])
  const currentNode = ref<OutlineNode | null>(null)
  const loading = ref(false)

  async function fetchNodes(projectId: number, nodeType?: string) {
    loading.value = true
    try {
      nodes.value = await getOutlineNodes(projectId, nodeType)
    } finally {
      loading.value = false
    }
  }

  async function fetchTree(projectId: number) {
    loading.value = true
    try {
      treeData.value = await getOutlineTree(projectId)
    } finally {
      loading.value = false
    }
  }

  async function createNode(projectId: number, data: CreateOutlineNodeData) {
    const node = await createOutlineNode(projectId, data)
    nodes.value.push(node)
    return node
  }

  async function updateNode(projectId: number, nodeId: number, data: UpdateOutlineNodeData) {
    const updated = await updateOutlineNode(projectId, nodeId, data)
    const index = nodes.value.findIndex(n => n.id === nodeId)
    if (index !== -1) {
      nodes.value[index] = updated
    }
    if (currentNode.value?.id === nodeId) {
      currentNode.value = updated
    }
    return updated
  }

  async function removeNode(projectId: number, nodeId: number) {
    await deleteOutlineNode(projectId, nodeId)
    nodes.value = nodes.value.filter(n => n.id !== nodeId)
    if (currentNode.value?.id === nodeId) {
      currentNode.value = null
    }
  }

  async function reorderNodes(projectId: number, orders: { id: number; sort_order: number; parent_id?: number }[]) {
    await reorderOutlineNodes(projectId, orders)
  }

  function setCurrentNode(node: OutlineNode | null) {
    currentNode.value = node
  }

  return {
    nodes,
    treeData,
    currentNode,
    loading,
    fetchNodes,
    fetchTree,
    createNode,
    updateNode,
    removeNode,
    reorderNodes,
    setCurrentNode,
  }
})