import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  streamWizardGenerate,
  createWizardProject,
} from '@/api/wizard'
import type {
  ChapterOutlineItem,
  CharacterOutlineItem,
} from '@/api/wizard'

export type GeneratePhase = 'idle' | 'generating' | 'outline' | 'characters' | 'done' | 'error' | 'cancelled'

export const useWizardStore = defineStore('wizard', () => {
  // 当前步骤 (1-4)
  const currentStep = ref(1)

  // 步骤 1：创作思路数据
  const ideaData = ref({
    title: '',
    genre: '',
    description: '',
    target_word_count: 100000,
    chapter_count: 10,
    reference_ids: [] as number[],
  })

  // 步骤 2：AI 生成的大纲和角色
  const outline = ref<ChapterOutlineItem[]>([])
  const characters = ref<CharacterOutlineItem[]>([])
  const generating = ref(false)
  const generateError = ref('')
  const generatePhase = ref<GeneratePhase>('idle')

  // 用于取消请求的 AbortController
  let abortController: AbortController | null = null

  // 步骤 3：选中的参考小说
  const selectedReferences = ref<number[]>([])

  // 步骤 4：创建结果
  const createdProjectId = ref<number | null>(null)
  const creating = ref(false)

  // 计算每章字数
  function getWordsPerChapter(): number {
    if (ideaData.value.chapter_count <= 0) return 0
    return Math.round(ideaData.value.target_word_count / ideaData.value.chapter_count)
  }

  // 生成大纲和角色
  async function generateOutlineAndCharacters() {
    generating.value = true
    generateError.value = ''
    generatePhase.value = 'generating'
    outline.value = []
    characters.value = []

    return new Promise<void>((resolve, reject) => {
      abortController = streamWizardGenerate(
        {
          title: ideaData.value.title,
          genre: ideaData.value.genre,
          description: ideaData.value.description,
          target_word_count: ideaData.value.target_word_count,
          chapter_count: ideaData.value.chapter_count,
          reference_ids: ideaData.value.reference_ids,
        },
        (event) => {
          if (event.type === 'progress') {
            // 进度消息
          } else if (event.type === 'outline' && event.data) {
            generatePhase.value = 'outline'
            outline.value = event.data as ChapterOutlineItem[]
          } else if (event.type === 'characters' && event.data) {
            generatePhase.value = 'characters'
            characters.value = event.data as CharacterOutlineItem[]
          } else if (event.type === 'done') {
            generatePhase.value = 'done'
            generating.value = false
            abortController = null
            resolve()
          }
        },
        (error) => {
          generating.value = false
          generatePhase.value = 'error'
          generateError.value = error
          abortController = null
          reject(new Error(error))
        },
      )
    })
  }

  // 取消生成
  function cancelGenerate() {
    if (abortController) {
      abortController.abort()
      abortController = null
      generating.value = false
      generatePhase.value = 'cancelled'
    }
  }

  // 更新大纲项
  function updateOutlineItem(index: number, item: ChapterOutlineItem) {
    if (index >= 0 && index < outline.value.length) {
      outline.value[index] = item
    }
  }

  // 添加大纲项
  function addOutlineItem(item: ChapterOutlineItem) {
    outline.value.push(item)
  }

  // 删除大纲项
  function removeOutlineItem(index: number) {
    if (index >= 0 && index < outline.value.length) {
      outline.value.splice(index, 1)
      // 重新编号
      outline.value.forEach((item, i) => {
        item.chapter = i + 1
      })
    }
  }

  // 更新角色项
  function updateCharacterItem(index: number, item: CharacterOutlineItem) {
    if (index >= 0 && index < characters.value.length) {
      characters.value[index] = item
    }
  }

  // 添加角色项
  function addCharacterItem(item: CharacterOutlineItem) {
    characters.value.push(item)
  }

  // 删除角色项
  function removeCharacterItem(index: number) {
    if (index >= 0 && index < characters.value.length) {
      characters.value.splice(index, 1)
    }
  }

  // 创建项目
  async function createProject() {
    creating.value = true
    try {
      const result = await createWizardProject({
        title: ideaData.value.title,
        genre: ideaData.value.genre,
        description: ideaData.value.description,
        target_word_count: ideaData.value.target_word_count,
        outline: outline.value,
        characters: characters.value,
        reference_ids: selectedReferences.value,
      })
      createdProjectId.value = result.project_id
      return result
    } finally {
      creating.value = false
    }
  }

  // 重置向导状态
  function reset() {
    // 取消正在进行的生成
    if (abortController) {
      abortController.abort()
      abortController = null
    }

    currentStep.value = 1
    ideaData.value = {
      title: '',
      genre: '',
      description: '',
      target_word_count: 100000,
      chapter_count: 10,
      reference_ids: [],
    }
    outline.value = []
    characters.value = []
    generating.value = false
    generateError.value = ''
    generatePhase.value = 'idle'
    selectedReferences.value = []
    createdProjectId.value = null
    creating.value = false
  }

  // 下一步
  function nextStep() {
    if (currentStep.value < 4) {
      currentStep.value++
    }
  }

  // 上一步
  function prevStep() {
    if (currentStep.value > 1) {
      currentStep.value--
    }
  }

  return {
    // 状态
    currentStep,
    ideaData,
    outline,
    characters,
    generating,
    generateError,
    generatePhase,
    selectedReferences,
    createdProjectId,
    creating,

    // 方法
    generateOutlineAndCharacters,
    cancelGenerate,
    getWordsPerChapter,
    updateOutlineItem,
    addOutlineItem,
    removeOutlineItem,
    updateCharacterItem,
    addCharacterItem,
    removeCharacterItem,
    createProject,
    reset,
    nextStep,
    prevStep,
  }
})