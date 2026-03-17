/**
 * AI 输出历史记录管理
 * 使用 localStorage 持久化存储
 */
import { ref } from 'vue'

export interface AIHistoryItem {
  id: string
  timestamp: number
  action: string
  actionLabel: string
  output: string
  wordCount: number
  chapterTitle?: string
  question?: string
}

const STORAGE_KEY = 'ai-output-history'
const MAX_HISTORY = 50

// 全局历史记录状态
const history = ref<AIHistoryItem[]>([])

// 从 localStorage 加载
function loadHistory(): AIHistoryItem[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      return JSON.parse(stored)
    }
  } catch {
    // 忽略解析错误
  }
  return []
}

// 保存到 localStorage
function saveHistory(items: AIHistoryItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, MAX_HISTORY)))
  } catch {
    // 存储满时清理旧数据
    const trimmed = items.slice(0, Math.floor(MAX_HISTORY / 2))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed))
  }
}

// 初始化加载
history.value = loadHistory()

/**
 * AI 历史记录 composable
 */
export function useAIHistory() {
  /**
   * 添加历史记录
   */
  function addHistory(item: Omit<AIHistoryItem, 'id' | 'timestamp' | 'wordCount'>) {
    const newItem: AIHistoryItem = {
      ...item,
      id: `ai-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      timestamp: Date.now(),
      wordCount: item.output.length,
    }

    history.value.unshift(newItem)
    saveHistory(history.value)
  }

  /**
   * 删除单条历史
   */
  function removeHistory(id: string) {
    history.value = history.value.filter(h => h.id !== id)
    saveHistory(history.value)
  }

  /**
   * 清空所有历史
   */
  function clearHistory() {
    history.value = []
    localStorage.removeItem(STORAGE_KEY)
  }

  /**
   * 获取最近的历史
   */
  function getRecentHistory(limit = 10) {
    return history.value.slice(0, limit)
  }

  /**
   * 按动作类型筛选
   */
  function filterByAction(action: string) {
    return history.value.filter(h => h.action === action)
  }

  /**
   * 搜索历史
   */
  function searchHistory(query: string) {
    const q = query.toLowerCase()
    return history.value.filter(h =>
      h.output.toLowerCase().includes(q) ||
      h.question?.toLowerCase().includes(q) ||
      h.chapterTitle?.toLowerCase().includes(q)
    )
  }

  return {
    history,
    addHistory,
    removeHistory,
    clearHistory,
    getRecentHistory,
    filterByAction,
    searchHistory,
  }
}

// 动作标签映射
export const ACTION_LABELS: Record<string, string> = {
  continue: '续写故事',
  rewrite: '改写润色',
  expand: '扩写内容',
  outline: '生成大纲',
  character_analysis: '角色分析',
  free_chat: '自由提问',
  analyze_expand: '开篇分析',
  revise: '意见修改',
  plot_enhance: '剧情完善',
  batch_generate: '批量写作',
}

/**
 * 获取动作标签
 */
export function getActionLabel(action: string): string {
  return ACTION_LABELS[action] || action
}