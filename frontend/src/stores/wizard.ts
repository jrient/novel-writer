import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  streamWizardOutline,
  createWizardProject,
  // 新的 API
  streamWizardMaps,
  streamWizardParts,
  streamWizardCharactersForPart,
  createWizardProjectV2,
  generateUUID,
} from '@/api/wizard'
import type {
  ChapterOutlineItem,
  CharacterOutlineItem,
  MapNode,
  PartNode,
  NoteItem,
} from '@/api/wizard'

const WIZARD_STORAGE_KEY = 'novel-wizard-draft'

export type GeneratePhase = 'idle' | 'generating' | 'maps' | 'parts' | 'outline' | 'characters' | 'done' | 'error' | 'cancelled'

export const useWizardStore = defineStore('wizard', () => {
  // ============ 新向导流程状态 ============

  // 当前步骤 (1-7)
  const currentStep = ref(1)

  // 步骤 1：创作思路数据（简化版，去掉章节数/字数）
  const ideaData = ref({
    title: '',
    genre: '',
    description: '',
    reference_ids: [] as number[],
  })

  // 步骤 2：地图数据
  const maps = ref<MapNode[]>([])
  const generatingMaps = ref(false)
  const mapsError = ref('')
  const mapsPhase = ref<GeneratePhase>('idle')

  // 当前选中的地图
  const selectedMapId = ref<string | null>(null)
  const selectedMap = computed(() => maps.value.find(m => m.id === selectedMapId.value))

  // 步骤 3：部分数据
  const generatingParts = ref(false)
  const partsError = ref('')
  const partsPhase = ref<GeneratePhase>('idle')

  // 步骤 4：角色库
  const characters = ref<CharacterOutlineItem[]>([])
  const generatingCharacters = ref(false)
  const charactersError = ref('')
  const charactersPhase = ref<GeneratePhase>('idle')

  // 步骤 5：笔记
  const notes = ref<NoteItem[]>([])

  // 步骤 6：创建结果
  const createdProjectId = ref<number | null>(null)
  const creating = ref(false)

  // 用于取消请求的 AbortController
  let mapsAbortController: AbortController | null = null
  let partsAbortController: AbortController | null = null
  let charactersAbortController: AbortController | null = null

  // ============ 旧流程状态（保留兼容） ============

  const outline = ref<ChapterOutlineItem[]>([])
  const generatingOutline = ref(false)
  const outlineError = ref('')
  const outlinePhase = ref<GeneratePhase>('idle')

  const generating = ref(false)
  const generateError = ref('')
  const generatePhase = ref<GeneratePhase>('idle')
  let outlineAbortController: AbortController | null = null
  let abortController: AbortController | null = null

  // 选中的参考小说
  const selectedReferences = ref<number[]>([])

  // ============ 新向导流程方法 ============

  // 步骤 2：生成地图
  async function generateMaps(revisionRequest?: string) {
    generatingMaps.value = true
    mapsError.value = ''
    mapsPhase.value = 'generating'

    const isRevision = !!revisionRequest && maps.value.length > 0
    if (!isRevision) {
      maps.value = []
    }

    return new Promise<void>((resolve, reject) => {
      mapsAbortController = streamWizardMaps(
        {
          title: ideaData.value.title,
          genre: ideaData.value.genre,
          description: ideaData.value.description,
          reference_ids: ideaData.value.reference_ids,
          revision_request: revisionRequest,
          current_maps: isRevision ? maps.value : undefined,
        },
        (event) => {
          if (event.type === 'progress') {
            // 进度消息
          } else if (event.type === 'maps' && event.data) {
            mapsPhase.value = 'maps'
            // 为每个地图分配 UUID
            const newMaps = event.data as MapNode[]
            maps.value = newMaps.map(m => ({
              ...m,
              id: String(m.id || generateUUID()),
              parts: m.parts || []
            }))
          } else if (event.type === 'done') {
            mapsPhase.value = 'done'
            generatingMaps.value = false
            mapsAbortController = null
            saveDraft()
            resolve()
          }
        },
        (error) => {
          generatingMaps.value = false
          mapsPhase.value = 'error'
          mapsError.value = error
          mapsAbortController = null
          reject(new Error(error))
        },
      )
    })
  }

  function cancelMapsGenerate() {
    if (mapsAbortController) {
      mapsAbortController.abort()
      mapsAbortController = null
      generatingMaps.value = false
      mapsPhase.value = 'cancelled'
    }
  }

  // 步骤 3：为选中的地图生成部分
  async function generatePartsForMap(mapId: string, revisionRequest?: string) {
    const mapItem = maps.value.find(m => m.id === mapId)
    if (!mapItem) {
      partsError.value = '请先选择一个地图'
      return
    }

    selectedMapId.value = mapId
    generatingParts.value = true
    partsError.value = ''
    partsPhase.value = 'generating'

    const isRevision = !!revisionRequest && mapItem.parts.length > 0
    if (!isRevision) {
      mapItem.parts = []
    }

    return new Promise<void>((resolve, reject) => {
      partsAbortController = streamWizardParts(
        {
          title: ideaData.value.title,
          genre: ideaData.value.genre,
          description: ideaData.value.description,
          map_id: mapId || '',
          map_name: mapItem.name,
          revision_request: revisionRequest,
          current_parts: isRevision ? mapItem.parts : undefined,
        },
        (event) => {
          if (event.type === 'progress') {
            // 进度消息
          } else if (event.type === 'parts' && event.data) {
            partsPhase.value = 'parts'
            // 更新选中地图的部分，分配 UUID
            const newParts = event.data as PartNode[]
            const mapIndex = maps.value.findIndex(m => m.id === mapId)
            if (mapIndex !== -1) {
              maps.value[mapIndex].parts = newParts.map(p => ({
                ...p,
                id: String(p.id || generateUUID()),
                chapters: p.chapters || [],
                character_ids: p.character_ids || []
              }))
            }
          } else if (event.type === 'done') {
            partsPhase.value = 'done'
            generatingParts.value = false
            partsAbortController = null
            saveDraft()
            resolve()
          }
        },
        (error) => {
          generatingParts.value = false
          partsPhase.value = 'error'
          partsError.value = error
          partsAbortController = null
          reject(new Error(error))
        },
      )
    })
  }

  function cancelPartsGenerate() {
    if (partsAbortController) {
      partsAbortController.abort()
      partsAbortController = null
      generatingParts.value = false
      partsPhase.value = 'cancelled'
    }
  }

  // 步骤 4：为所有地图的所有部分生成角色
  async function generateCharactersForAllParts() {
    // 收集所有部分
    const allParts: PartNode[] = []
    for (const mapItem of maps.value) {
      allParts.push(...mapItem.parts)
    }

    if (allParts.length === 0) {
      charactersError.value = '请先生成部分'
      return
    }

    generatingCharacters.value = true
    charactersError.value = ''
    charactersPhase.value = 'generating'

    return new Promise<void>((resolve, reject) => {
      charactersAbortController = streamWizardCharactersForPart(
        {
          title: ideaData.value.title,
          genre: ideaData.value.genre,
          description: ideaData.value.description,
          parts: allParts,
          existing_characters: characters.value,
        },
        (event) => {
          if (event.type === 'progress') {
            // 进度消息
          } else if (event.type === 'characters' && event.data) {
            charactersPhase.value = 'characters'
            // 合并新角色（避免重复），分配 UUID
            const newChars = event.data as CharacterOutlineItem[]
            for (const char of newChars) {
              const exists = characters.value.find(c => c.name === char.name)
              if (!exists) {
                characters.value.push({
                  ...char,
                  id: String(char.id || generateUUID()),
                  origin_map_id: selectedMapId.value ? String(selectedMapId.value) : undefined
                })
              }
            }
          } else if (event.type === 'done') {
            charactersPhase.value = 'done'
            generatingCharacters.value = false
            charactersAbortController = null
            saveDraft()
            resolve()
          }
        },
        (error) => {
          generatingCharacters.value = false
          charactersPhase.value = 'error'
          charactersError.value = error
          charactersAbortController = null
          reject(new Error(error))
        },
      )
    })
  }

  function cancelCharactersGenerate() {
    if (charactersAbortController) {
      charactersAbortController.abort()
      charactersAbortController = null
      generatingCharacters.value = false
      charactersPhase.value = 'cancelled'
    }
  }

  // 步骤 5：添加笔记
  function addNote(note: NoteItem) {
    notes.value.push(note)
  }

  function removeNote(index: number) {
    if (index >= 0 && index < notes.value.length) {
      notes.value.splice(index, 1)
    }
  }

  function updateNote(index: number, note: NoteItem) {
    if (index >= 0 && index < notes.value.length) {
      notes.value[index] = note
    }
  }

  // 步骤 6：创建项目
  async function createProjectV2() {
    creating.value = true
    try {
      const result = await createWizardProjectV2({
        title: ideaData.value.title,
        genre: ideaData.value.genre,
        description: ideaData.value.description,
        maps: maps.value,
        characters: characters.value,
        notes: notes.value.length > 0 ? notes.value : undefined,
        reference_ids: selectedReferences.value,
      })
      createdProjectId.value = result.project_id
      return result
    } finally {
      creating.value = false
    }
  }

  // ============ 地图/部分/章节编辑方法 ============

  function updateMap(mapId: string, data: Partial<MapNode>) {
    const index = maps.value.findIndex(m => m.id === mapId)
    if (index !== -1) {
      maps.value[index] = { ...maps.value[index], ...data }
    }
  }

  function removeMap(mapId: string) {
    const index = maps.value.findIndex(m => m.id === mapId)
    if (index !== -1) {
      maps.value.splice(index, 1)
      if (selectedMapId.value === mapId) {
        selectedMapId.value = null
      }
    }
  }

  function addPartToMap(mapId: string, part: PartNode) {
    const mapItem = maps.value.find(m => m.id === mapId)
    if (mapItem) {
      part.id = String(part.id || generateUUID())
      mapItem.parts.push(part)
    }
  }

  function updatePartInMap(mapId: string, partId: string, data: Partial<PartNode>) {
    const mapItem = maps.value.find(m => m.id === mapId)
    if (mapItem) {
      const partIndex = mapItem.parts.findIndex(p => p.id === partId)
      if (partIndex !== -1) {
        mapItem.parts[partIndex] = { ...mapItem.parts[partIndex], ...data }
      }
    }
  }

  function removePartFromMap(mapId: string, partId: string) {
    const mapItem = maps.value.find(m => m.id === mapId)
    if (mapItem) {
      const partIndex = mapItem.parts.findIndex(p => p.id === partId)
      if (partIndex !== -1) {
        mapItem.parts.splice(partIndex, 1)
      }
    }
  }

  // ============ 角色编辑方法 ============

  function updateCharacterItem(index: number, item: CharacterOutlineItem) {
    if (index >= 0 && index < characters.value.length) {
      characters.value[index] = item
    }
  }

  function addCharacterItem(item: CharacterOutlineItem) {
    characters.value.push(item)
  }

  function removeCharacterItem(index: number) {
    if (index >= 0 && index < characters.value.length) {
      characters.value.splice(index, 1)
    }
  }

  // ============ 旧流程方法（保留兼容） ============

  async function generateOutline(revisionRequest?: string) {
    generatingOutline.value = true
    outlineError.value = ''
    outlinePhase.value = 'generating'
    generating.value = true
    generatePhase.value = 'generating'

    const isRevision = !!revisionRequest && outline.value.length > 0
    if (!isRevision) {
      outline.value = []
    }

    return new Promise<void>((resolve, reject) => {
      outlineAbortController = streamWizardOutline(
        {
          title: ideaData.value.title,
          genre: ideaData.value.genre,
          description: ideaData.value.description,
          target_word_count: 100000,
          chapter_count: 10,
          reference_ids: ideaData.value.reference_ids,
          revision_request: revisionRequest,
          current_outline: isRevision ? outline.value : undefined,
        },
        (event) => {
          if (event.type === 'outline' && event.data) {
            outlinePhase.value = 'outline'
            generatePhase.value = 'outline'
            outline.value = event.data as ChapterOutlineItem[]
          } else if (event.type === 'done') {
            outlinePhase.value = 'done'
            generatePhase.value = 'done'
            generatingOutline.value = false
            generating.value = false
            outlineAbortController = null
            resolve()
          }
        },
        (error) => {
          generatingOutline.value = false
          generating.value = false
          outlinePhase.value = 'error'
          generatePhase.value = 'error'
          outlineError.value = error
          generateError.value = error
          outlineAbortController = null
          reject(new Error(error))
        },
      )
    })
  }

  function cancelOutlineGenerate() {
    if (outlineAbortController) {
      outlineAbortController.abort()
      outlineAbortController = null
      generatingOutline.value = false
      generating.value = false
      outlinePhase.value = 'cancelled'
      generatePhase.value = 'cancelled'
    }
  }

  async function createProject() {
    creating.value = true
    try {
      const outlineText = outline.value.map(item => `第${item.chapter}章 ${item.title}\n${item.summary}`).join('\n\n')
      const result = await createWizardProject({
        title: ideaData.value.title,
        genre: ideaData.value.genre,
        description: ideaData.value.description,
        target_word_count: 100000,
        outline: outline.value,
        characters: characters.value,
        reference_ids: selectedReferences.value,
        outline_text: outlineText,
      })
      createdProjectId.value = result.project_id
      return result
    } finally {
      creating.value = false
    }
  }

  // ============ 通用方法 ============

  function cancelGenerate() {
    cancelMapsGenerate()
    cancelPartsGenerate()
    cancelCharactersGenerate()
    cancelOutlineGenerate()
    if (abortController) {
      abortController.abort()
      abortController = null
      generating.value = false
      generatePhase.value = 'cancelled'
    }
  }

  // ============ 草稿持久化 ============

  function saveDraft() {
    try {
      const draft = {
        currentStep: currentStep.value,
        ideaData: ideaData.value,
        maps: maps.value,
        selectedMapId: selectedMapId.value,
        characters: characters.value,
        notes: notes.value,
        createdProjectId: createdProjectId.value,
        savedAt: new Date().toISOString()
      }
      localStorage.setItem(WIZARD_STORAGE_KEY, JSON.stringify(draft))
    } catch (e) {
      console.warn('保存向导草稿失败:', e)
    }
  }

  function loadDraft(): boolean {
    try {
      const data = localStorage.getItem(WIZARD_STORAGE_KEY)
      if (!data) return false

      const draft = JSON.parse(data)
      currentStep.value = draft.currentStep || 1
      ideaData.value = draft.ideaData || { title: '', genre: '', description: '', reference_ids: [] }
      maps.value = draft.maps || []
      selectedMapId.value = draft.selectedMapId || null
      characters.value = draft.characters || []
      notes.value = draft.notes || []
      createdProjectId.value = draft.createdProjectId || null
      return true
    } catch (e) {
      console.warn('加载向导草稿失败:', e)
      return false
    }
  }

  function clearDraft() {
    try {
      localStorage.removeItem(WIZARD_STORAGE_KEY)
    } catch (e) {
      console.warn('清除向导草稿失败:', e)
    }
  }

  function reset() {
    cancelGenerate()

    currentStep.value = 1
    ideaData.value = {
      title: '',
      genre: '',
      description: '',
      reference_ids: [],
    }
    maps.value = []
    selectedMapId.value = null
    characters.value = []
    notes.value = []
    outline.value = []

    // 重置所有状态
    generatingMaps.value = false
    mapsError.value = ''
    mapsPhase.value = 'idle'
    generatingParts.value = false
    partsError.value = ''
    partsPhase.value = 'idle'
    generatingCharacters.value = false
    charactersError.value = ''
    charactersPhase.value = 'idle'
    generatingOutline.value = false
    outlineError.value = ''
    outlinePhase.value = 'idle'
    generating.value = false
    generateError.value = ''
    generatePhase.value = 'idle'

    selectedReferences.value = []
    createdProjectId.value = null
    creating.value = false

    // 清除草稿
    clearDraft()
  }

  function nextStep() {
    if (currentStep.value < 7) {
      currentStep.value++
      saveDraft()
    }
  }

  function prevStep() {
    if (currentStep.value > 1) {
      currentStep.value--
    }
  }

  // 计算总章节数
  const totalChapters = computed(() => {
    let count = 0
    for (const mapItem of maps.value) {
      for (const part of mapItem.parts) {
        count += part.chapters.length
      }
    }
    return count
  })

  return {
    // 状态
    currentStep,
    ideaData,
    maps,
    selectedMapId,
    selectedMap,
    characters,
    notes,
    outline,
    generatingMaps,
    mapsError,
    mapsPhase,
    generatingParts,
    partsError,
    partsPhase,
    generatingCharacters,
    charactersError,
    charactersPhase,
    generatingOutline,
    outlineError,
    outlinePhase,
    generating,
    generateError,
    generatePhase,
    selectedReferences,
    createdProjectId,
    creating,
    totalChapters,

    // 新流程方法
    generateMaps,
    cancelMapsGenerate,
    generatePartsForMap,
    cancelPartsGenerate,
    generateCharactersForAllParts,
    cancelCharactersGenerate,
    addNote,
    removeNote,
    updateNote,
    createProjectV2,

    // 地图/部分编辑方法
    updateMap,
    removeMap,
    addPartToMap,
    updatePartInMap,
    removePartFromMap,

    // 角色编辑方法
    updateCharacterItem,
    addCharacterItem,
    removeCharacterItem,

    // 旧流程方法（保留兼容）
    generateOutline,
    cancelOutlineGenerate,
    createProject,

    // 通用方法
    cancelGenerate,
    reset,
    nextStep,
    prevStep,

    // 草稿持久化
    saveDraft,
    loadDraft,
    clearDraft,
  }
})