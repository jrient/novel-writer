/**
 * AI 提示词模板系统
 * 预定义常用提示词模板，支持自定义
 */
import { ref } from 'vue'

export interface PromptTemplate {
  id: string
  name: string
  description: string
  category: 'creative' | 'revision' | 'analysis' | 'custom'
  prompt: string
  variables?: string[] // 模板中的变量，如 {{角色名}}
  isBuiltIn?: boolean
}

const STORAGE_KEY = 'ai-prompt-templates'

// 内置模板
const BUILT_IN_TEMPLATES: PromptTemplate[] = [
  {
    id: 'builtin-continue-suspense',
    name: '悬疑续写',
    description: '以悬疑风格续写，注重氛围营造',
    category: 'creative',
    prompt: '请以悬疑小说的风格续写以下内容，注意营造紧张氛围，埋下伏笔，让读者产生期待感：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-continue-romance',
    name: '言情续写',
    description: '以言情风格续写，注重情感描写',
    category: 'creative',
    prompt: '请以言情小说的风格续写以下内容，注重人物情感的细腻描写和心理活动：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-continue-fantasy',
    name: '玄幻续写',
    description: '以玄幻风格续写，注重世界观展现',
    category: 'creative',
    prompt: '请以玄幻小说的风格续写以下内容，注重展现独特的世界观、修炼体系和精彩的战斗场面：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-revise-concise',
    name: '精简润色',
    description: '删除冗余，使文字更加精炼',
    category: 'revision',
    prompt: '请对以下内容进行精简润色，删除冗余的表达，保留核心意思，使文字更加精炼有力：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-revise-descriptive',
    name: '增强描写',
    description: '增加细节描写，使场景更生动',
    category: 'revision',
    prompt: '请对以下内容进行扩充润色，增加环境描写、动作细节和心理活动，使场景更加生动：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-revise-dialogue',
    name: '优化对话',
    description: '优化对话，使其更自然',
    category: 'revision',
    prompt: '请优化以下内容中的对话部分，使对话更加自然、符合人物性格，并增加适当的动作和神态描写：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-analysis-character',
    name: '人物塑造分析',
    description: '分析人物形象是否鲜明',
    category: 'analysis',
    prompt: '请分析以下内容中的人物塑造，评估人物形象是否鲜明、性格是否一致，并提供改进建议：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-analysis-plot',
    name: '情节节奏分析',
    description: '分析情节节奏是否合理',
    category: 'analysis',
    prompt: '请分析以下内容的情节节奏，评估起承转合是否合理、是否有足够的冲突和悬念，并提供改进建议：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
  {
    id: 'builtin-analysis-setting',
    name: '世界观一致性检查',
    description: '检查设定是否前后一致',
    category: 'analysis',
    prompt: '请检查以下内容的世界观设定是否前后一致，是否存在逻辑漏洞，并提供修正建议：\n\n{{内容}}',
    variables: ['内容'],
    isBuiltIn: true,
  },
]

// 全局模板状态
const templates = ref<PromptTemplate[]>([])

// 从 localStorage 加载自定义模板
function loadTemplates(): PromptTemplate[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const custom = JSON.parse(stored) as PromptTemplate[]
      return [...BUILT_IN_TEMPLATES, ...custom]
    }
  } catch {
    // 忽略解析错误
  }
  return [...BUILT_IN_TEMPLATES]
}

// 保存自定义模板
function saveCustomTemplates(items: PromptTemplate[]) {
  const custom = items.filter(t => !t.isBuiltIn)
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(custom))
  } catch {
    // 忽略存储错误
  }
}

// 初始化
templates.value = loadTemplates()

/**
 * 提示词模板 composable
 */
export function usePromptTemplates() {
  /**
   * 按类别获取模板
   */
  function getTemplatesByCategory(category: PromptTemplate['category']) {
    return templates.value.filter(t => t.category === category)
  }

  /**
   * 添加自定义模板
   */
  function addTemplate(template: Omit<PromptTemplate, 'id' | 'isBuiltIn'>) {
    const newTemplate: PromptTemplate = {
      ...template,
      id: `custom-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      isBuiltIn: false,
    }
    templates.value.push(newTemplate)
    saveCustomTemplates(templates.value)
    return newTemplate
  }

  /**
   * 更新自定义模板
   */
  function updateTemplate(id: string, updates: Partial<PromptTemplate>) {
    const index = templates.value.findIndex(t => t.id === id)
    if (index !== -1 && !templates.value[index].isBuiltIn) {
      templates.value[index] = { ...templates.value[index], ...updates }
      saveCustomTemplates(templates.value)
    }
  }

  /**
   * 删除自定义模板
   */
  function removeTemplate(id: string) {
    const template = templates.value.find(t => t.id === id)
    if (template && !template.isBuiltIn) {
      templates.value = templates.value.filter(t => t.id !== id)
      saveCustomTemplates(templates.value)
    }
  }

  /**
   * 应用模板，替换变量
   */
  function applyTemplate(template: PromptTemplate, variables: Record<string, string>): string {
    let result = template.prompt
    for (const [key, value] of Object.entries(variables)) {
      result = result.replace(new RegExp(`{{${key}}}`, 'g'), value)
    }
    return result
  }

  /**
   * 获取模板分类标签
   */
  function getCategoryLabel(category: PromptTemplate['category']): string {
    const labels: Record<string, string> = {
      creative: '创作',
      revision: '润色',
      analysis: '分析',
      custom: '自定义',
    }
    return labels[category] || category
  }

  return {
    templates,
    getTemplatesByCategory,
    addTemplate,
    updateTemplate,
    removeTemplate,
    applyTemplate,
    getCategoryLabel,
  }
}