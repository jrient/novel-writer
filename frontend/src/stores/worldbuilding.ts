import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getWorldbuilding,
  getWorldbuildingTree,
  createWorldbuilding,
  updateWorldbuilding,
  deleteWorldbuilding,
} from '@/api/worldbuilding'
import type { WorldbuildingEntry, CreateWorldbuildingData, UpdateWorldbuildingData } from '@/api/worldbuilding'

export const useWorldbuildingStore = defineStore('worldbuilding', () => {
  const entries = ref<WorldbuildingEntry[]>([])
  const treeData = ref<WorldbuildingEntry[]>([])
  const currentEntry = ref<WorldbuildingEntry | null>(null)
  const loading = ref(false)

  async function fetchEntries(projectId: number, category?: string) {
    loading.value = true
    try {
      entries.value = await getWorldbuilding(projectId, category)
    } finally {
      loading.value = false
    }
  }

  async function fetchTree(projectId: number) {
    loading.value = true
    try {
      treeData.value = await getWorldbuildingTree(projectId)
    } finally {
      loading.value = false
    }
  }

  async function createEntry(projectId: number, data: CreateWorldbuildingData) {
    const entry = await createWorldbuilding(projectId, data)
    entries.value.push(entry)
    return entry
  }

  async function updateEntry(projectId: number, entryId: number, data: UpdateWorldbuildingData) {
    const updated = await updateWorldbuilding(projectId, entryId, data)
    const index = entries.value.findIndex(e => e.id === entryId)
    if (index !== -1) {
      entries.value[index] = updated
    }
    if (currentEntry.value?.id === entryId) {
      currentEntry.value = updated
    }
    return updated
  }

  async function removeEntry(projectId: number, entryId: number) {
    await deleteWorldbuilding(projectId, entryId)
    entries.value = entries.value.filter(e => e.id !== entryId)
    if (currentEntry.value?.id === entryId) {
      currentEntry.value = null
    }
  }

  function setCurrentEntry(entry: WorldbuildingEntry | null) {
    currentEntry.value = entry
  }

  return {
    entries,
    treeData,
    currentEntry,
    loading,
    fetchEntries,
    fetchTree,
    createEntry,
    updateEntry,
    removeEntry,
    setCurrentEntry,
  }
})