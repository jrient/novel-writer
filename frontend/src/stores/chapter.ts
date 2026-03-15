import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getChapters,
  createChapter,
  updateChapter,
  deleteChapter,
  batchDeleteChapters,
  reorderChapters,
} from '@/api/chapter'
import type { Chapter, CreateChapterData, UpdateChapterData, ChapterOrder } from '@/api/chapter'

export const useChapterStore = defineStore('chapter', () => {
  // 状态
  const chapters = ref<Chapter[]>([])
  const currentChapter = ref<Chapter | null>(null)
  const saving = ref(false)

  // 获取章节列表（按 sort_order 排序）
  async function fetchChapters(projectId: number) {
    const data = await getChapters(projectId)
    chapters.value = data.sort((a, b) => b.sort_order - a.sort_order)
  }

  // 创建章节
  async function createNewChapter(projectId: number, data: CreateChapterData) {
    // 默认 sort_order 排在最后
    const maxOrder = chapters.value.length > 0
      ? Math.max(...chapters.value.map((c) => c.sort_order))
      : 0
    const chapter = await createChapter(projectId, {
      ...data,
      sort_order: data.sort_order ?? maxOrder + 1,
    })
    chapters.value.push(chapter)
    chapters.value.sort((a, b) => b.sort_order - a.sort_order)
    return chapter
  }

  // 更新章节内容（带 saving 状态）
  async function updateCurrentChapter(
    projectId: number,
    chapterId: number,
    data: UpdateChapterData
  ) {
    saving.value = true
    try {
      const updated = await updateChapter(projectId, chapterId, data)
      // 同步更新列表
      const index = chapters.value.findIndex((c) => c.id === chapterId)
      if (index !== -1) {
        chapters.value[index] = updated
      }
      if (currentChapter.value?.id === chapterId) {
        currentChapter.value = updated
      }
      return updated
    } finally {
      saving.value = false
    }
  }

  // 删除章节（删除后自动选中相邻章节）
  async function removeChapter(projectId: number, chapterId: number) {
    const index = chapters.value.findIndex((c) => c.id === chapterId)
    await deleteChapter(projectId, chapterId)
    chapters.value = chapters.value.filter((c) => c.id !== chapterId)
    if (currentChapter.value?.id === chapterId) {
      if (chapters.value.length > 0) {
        const nextIndex = Math.min(index, chapters.value.length - 1)
        currentChapter.value = chapters.value[nextIndex]
      } else {
        currentChapter.value = null
      }
    }
  }

  // 批量删除章节
  async function removeChapters(projectId: number, chapterIds: number[]) {
    await batchDeleteChapters(projectId, chapterIds)
    chapters.value = chapters.value.filter((c) => !chapterIds.includes(c.id))
    if (currentChapter.value && chapterIds.includes(currentChapter.value.id)) {
      currentChapter.value = chapters.value.length > 0 ? chapters.value[0] : null
    }
  }

  // 设置当前编辑章节
  function setCurrentChapter(chapter: Chapter | null) {
    currentChapter.value = chapter
  }

  // 重新排序章节
  async function reorderCurrentChapters(projectId: number, orders: ChapterOrder[]) {
    await reorderChapters(projectId, orders)
    // 本地同步排序
    orders.forEach(({ id, sort_order }) => {
      const chapter = chapters.value.find((c) => c.id === id)
      if (chapter) chapter.sort_order = sort_order
    })
    chapters.value.sort((a, b) => b.sort_order - a.sort_order)
  }

  return {
    chapters,
    currentChapter,
    saving,
    fetchChapters,
    createNewChapter,
    updateCurrentChapter,
    removeChapter,
    removeChapters,
    setCurrentChapter,
    reorderCurrentChapters,
  }
})
