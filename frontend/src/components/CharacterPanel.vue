<template>
  <div class="character-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">角色管理</span>
      <div class="header-buttons">
        <el-button
          size="small"
          type="success"
          plain
          :icon="Reading"
          :loading="extracting"
          @click="extractCharacters"
        >
          从章节提取
        </el-button>
        <el-button size="small" type="primary" :icon="Plus" @click="showCreateDialog = true">
          新建角色
        </el-button>
      </div>
    </div>

    <!-- 角色类型筛选 -->
    <div class="filter-bar">
      <el-radio-group v-model="filterRoleType" size="small" @change="handleFilter">
        <el-radio-button label="">全部</el-radio-button>
        <el-radio-button label="protagonist">主角</el-radio-button>
        <el-radio-button label="antagonist">反派</el-radio-button>
        <el-radio-button label="supporting">配角</el-radio-button>
      </el-radio-group>
    </div>

    <!-- AI 角色分析 -->
    <div class="ai-analysis-bar">
      <el-button
        size="small"
        type="warning"
        plain
        :icon="MagicStick"
        :loading="analyzing"
        :disabled="!currentCharacter"
        @click="analyzeCharacter"
      >
        AI 角色分析
      </el-button>
      <span v-if="!currentCharacter" class="analysis-hint">请先选择角色</span>
    </div>

    <!-- 角色分析结果 -->
    <div v-if="analysisResult" class="analysis-result">
      <div class="analysis-header">
        <span class="analysis-title">角色分析结果</span>
        <el-button size="small" text @click="analysisResult = ''">关闭</el-button>
      </div>
      <div class="analysis-content" v-html="renderMarkdown(analysisResult)"></div>
    </div>

    <!-- 角色列表 -->
    <div class="character-list">
      <div v-if="characterStore.loading" class="loading-state">
        <el-skeleton :rows="2" animated />
      </div>

      <div v-else-if="filteredCharacters.length === 0" class="empty-state">
        <el-empty description="暂无角色" :image-size="60" />
      </div>

      <div
        v-else
        v-for="character in filteredCharacters"
        :key="character.id"
        class="character-card"
        :class="{ active: currentCharacter?.id === character.id }"
        @click="selectCharacter(character)"
      >
        <div class="avatar-section">
          <el-avatar :size="48" :src="character.avatar_url || undefined">
            {{ character.name.charAt(0) }}
          </el-avatar>
        </div>
        <div class="info-section">
          <div class="name-row">
            <span class="name">{{ character.name }}</span>
            <el-tag :type="roleTagType(character.role_type)" size="small">
              {{ roleLabel(character.role_type) }}
            </el-tag>
          </div>
          <div class="meta-row">
            <span v-if="character.age">{{ character.age }}</span>
            <span v-if="character.gender">{{ character.gender }}</span>
            <span v-if="character.occupation">{{ character.occupation }}</span>
          </div>
        </div>
        <div class="actions">
          <el-button text size="small" :icon="Edit" @click.stop="editCharacter(character)" />
          <el-button text size="small" type="danger" :icon="Delete" @click.stop="confirmDelete(character)" />
        </div>
      </div>
    </div>

    <!-- 章节选择对话框 -->
    <el-dialog
      v-model="showChapterSelectDialog"
      title="选择要分析的章节"
      width="500px"
      :close-on-click-modal="false"
    >
      <div class="chapter-select-hint">
        请勾选需要提取角色的章节（最多选择 10 章）
      </div>
      <div class="chapter-select-list">
        <el-checkbox-group v-model="selectedChapterIds">
          <div
            v-for="ch in chaptersForSelect"
            :key="ch.id"
            class="chapter-select-item"
          >
            <el-checkbox
              :value="ch.id"
              :disabled="!selectedChapterIds.includes(ch.id) && selectedChapterIds.length >= 10"
            >
              <span class="chapter-select-title">{{ ch.title }}</span>
              <span class="chapter-select-words">{{ ch.word_count }} 字</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
        <div v-if="chaptersForSelect.length === 0" class="chapter-select-empty">
          暂无章节内容
        </div>
      </div>
      <template #footer>
        <div class="chapter-select-footer">
          <span class="chapter-select-count">已选 {{ selectedChapterIds.length }} / 10 章</span>
          <div>
            <el-button @click="showChapterSelectDialog = false">取消</el-button>
            <el-button
              type="primary"
              :loading="extracting"
              :disabled="selectedChapterIds.length === 0"
              @click="doExtractCharacters"
            >
              开始提取
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 角色详情/编辑对话框 -->
    <el-dialog
      :close-on-press-escape="false"
      v-model="showEditDialog"
      :title="editingCharacter ? '编辑角色' : '新建角色'"
      width="700px"
      :close-on-click-modal="false"
    >
      <el-form :model="formData" label-width="80px" label-position="left">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="姓名" required>
              <el-input v-model="formData.name" placeholder="角色姓名" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="类型">
              <el-select v-model="formData.role_type" style="width: 100%">
                <el-option label="主角" value="protagonist" />
                <el-option label="反派" value="antagonist" />
                <el-option label="配角" value="supporting" />
                <el-option label="次要角色" value="minor" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="年龄">
              <el-input v-model="formData.age" placeholder="如: 25岁" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="性别">
              <el-input v-model="formData.gender" placeholder="男/女" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="身份">
              <el-input v-model="formData.occupation" placeholder="职业/身份" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="外貌">
          <el-input v-model="formData.appearance" type="textarea" :rows="2" placeholder="角色外貌描写..." />
        </el-form-item>

        <el-form-item label="性格">
          <el-input v-model="formData.personality_traits" type="textarea" :rows="2" placeholder="性格特点..." />
        </el-form-item>

        <el-form-item label="背景">
          <el-input v-model="formData.background" type="textarea" :rows="3" placeholder="角色背景故事..." />
        </el-form-item>

        <el-form-item label="成长弧线">
          <el-input v-model="formData.growth_arc" type="textarea" :rows="2" placeholder="角色发展轨迹..." />
        </el-form-item>

        <el-form-item label="备注">
          <el-input v-model="formData.notes" type="textarea" :rows="2" placeholder="其他备注..." />
        </el-form-item>
      </el-form>

      <template #footer>
        <div class="dialog-footer">
          <el-button
            type="warning"
            plain
            :icon="MagicStick"
            :loading="polishing"
            @click="polishCharacter"
            :disabled="!formData.name"
          >
            AI 润色
          </el-button>
          <div class="footer-right">
            <el-button @click="showEditDialog = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="saveCharacter">保存</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Edit, Delete, MagicStick, Reading } from '@element-plus/icons-vue'
import { useCharacterStore } from '@/stores/character'
import { useChapterStore } from '@/stores/chapter'
import type { Character, CreateCharacterData, UpdateCharacterData } from '@/api/character'
import { createCharacter } from '@/api/character'
import { streamGenerate } from '@/api/ai'

const props = defineProps<{
  projectId: number
}>()

const characterStore = useCharacterStore()
const chapterStore = useChapterStore()

// 从章节提取角色
const extracting = ref(false)
const showChapterSelectDialog = ref(false)
const selectedChapterIds = ref<number[]>([])

// 章节列表（按 sort_order 倒序，只保留有内容的）
const chaptersForSelect = computed(() => {
  return [...chapterStore.chapters]
    .sort((a, b) => b.sort_order - a.sort_order)
    .filter(ch => ch.content && ch.word_count > 0)
})

async function extractCharacters() {
  // 确保已加载章节列表
  if (chapterStore.chapters.length === 0) {
    await chapterStore.fetchChapters(props.projectId)
  }
  if (chaptersForSelect.value.length === 0) {
    ElMessage.warning('项目中没有章节内容，无法提取角色')
    return
  }
  selectedChapterIds.value = []
  showChapterSelectDialog.value = true
}

function doExtractCharacters() {
  extracting.value = true
  let result = ''

  streamGenerate(
    props.projectId,
    {
      action: 'extract_characters',
      content: '',
      chapter_ids: selectedChapterIds.value,
    },
    (text) => {
      result += text
    },
    () => {
      showChapterSelectDialog.value = false
      processExtractedCharacters(result)
    },
    (error) => {
      extracting.value = false
      ElMessage.error(`提取失败: ${error}`)
    }
  )
}

async function processExtractedCharacters(result: string) {
  try {
    // 尝试从返回文本中提取 JSON 数组
    let jsonStr = result.trim()
    const match = jsonStr.match(/\[[\s\S]*\]/)
    if (match) {
      jsonStr = match[0]
    }
    const characters = JSON.parse(jsonStr) as Array<{
      name: string
      role_type?: string
      gender?: string
      age?: string
      occupation?: string
      personality_traits?: string
      appearance?: string
      background?: string
    }>

    if (!Array.isArray(characters) || characters.length === 0) {
      ElMessage.info('未从章节中提取到新角色')
      return
    }

    let created = 0
    for (const char of characters) {
      if (!char.name) continue
      try {
        await createCharacter(props.projectId, {
          name: char.name,
          role_type: char.role_type || 'supporting',
          gender: char.gender || '',
          age: char.age || '',
          occupation: char.occupation || '',
          personality_traits: char.personality_traits || '',
          appearance: char.appearance || '',
          background: char.background || '',
        })
        created++
      } catch {
        // 单个角色创建失败不影响整体
      }
    }

    // 刷新角色列表
    await characterStore.fetchCharacters(props.projectId)
    ElMessage.success(`成功提取并创建 ${created} 个新角色`)
  } catch {
    ElMessage.error('解析 AI 返回的角色数据失败，请重试')
  } finally {
    extracting.value = false
  }
}

// AI 角色分析
const analyzing = ref(false)
const analysisResult = ref('')

function renderMarkdown(text: string): string {
  return text
    .replace(/### (.+)/g, '<h4>$1</h4>')
    .replace(/## (.+)/g, '<h3>$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n- /g, '\n<br>• ')
    .replace(/\n(\d+)\. /g, '\n<br>$1. ')
    .replace(/\n/g, '<br>')
}

async function analyzeCharacter() {
  const char = currentCharacter.value
  if (!char) return

  analyzing.value = true
  analysisResult.value = ''

  const content = [
    `姓名：${char.name}`,
    `类型：${roleLabel(char.role_type)}`,
    char.age ? `年龄：${char.age}` : '',
    char.gender ? `性别：${char.gender}` : '',
    char.occupation ? `身份：${char.occupation}` : '',
    char.appearance ? `外貌：${char.appearance}` : '',
    char.personality_traits ? `性格：${char.personality_traits}` : '',
    char.background ? `背景：${char.background}` : '',
    char.growth_arc ? `成长弧线：${char.growth_arc}` : '',
    char.notes ? `备注：${char.notes}` : '',
  ].filter(Boolean).join('\n')

  streamGenerate(
    props.projectId,
    {
      action: 'character_analysis',
      content,
    },
    (text) => {
      analysisResult.value += text
    },
    () => {
      analyzing.value = false
      ElMessage.success('角色分析完成')
    },
    (error) => {
      analyzing.value = false
      ElMessage.error(`分析失败: ${error}`)
    }
  )
}

const filterRoleType = ref('')
const currentCharacter = computed(() => characterStore.currentCharacter)

const filteredCharacters = computed(() => {
  if (!filterRoleType.value) return characterStore.characters
  return characterStore.characters.filter(c => c.role_type === filterRoleType.value)
})

// 对话框状态
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const editingCharacter = ref<Character | null>(null)
const saving = ref(false)
const polishing = ref(false)

// 表单数据
const formData = ref<CreateCharacterData & UpdateCharacterData>({
  name: '',
  role_type: 'supporting',
  age: '',
  gender: '',
  occupation: '',
  appearance: '',
  personality_traits: '',
  background: '',
  growth_arc: '',
  notes: '',
})

function roleTagType(role: string) {
  const map: Record<string, string> = {
    protagonist: 'success',
    antagonist: 'danger',
    supporting: 'warning',
    minor: 'info',
  }
  return map[role] || 'info'
}

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    protagonist: '主角',
    antagonist: '反派',
    supporting: '配角',
    minor: '次要',
  }
  return map[role] || role || '配角'
}

function handleFilter() {
  characterStore.fetchCharacters(props.projectId, filterRoleType.value)
}

function selectCharacter(character: Character) {
  characterStore.setCurrentCharacter(character)
}

function editCharacter(character: Character) {
  editingCharacter.value = character
  formData.value = {
    name: character.name,
    role_type: character.role_type || 'supporting',
    age: character.age || '',
    gender: character.gender || '',
    occupation: character.occupation || '',
    appearance: character.appearance || '',
    personality_traits: character.personality_traits || '',
    background: character.background || '',
    growth_arc: character.growth_arc || '',
    notes: character.notes || '',
  }
  showEditDialog.value = true
}

async function saveCharacter() {
  if (!formData.value.name) return

  saving.value = true
  try {
    if (editingCharacter.value) {
      await characterStore.updateCurrentCharacter(
        props.projectId,
        editingCharacter.value.id,
        formData.value
      )
    } else {
      await characterStore.createNewCharacter(props.projectId, formData.value)
    }
    showEditDialog.value = false
    showCreateDialog.value = false
    resetForm()
  } finally {
    saving.value = false
  }
}

async function confirmDelete(character: Character) {
  await ElMessageBox.confirm(`确定要删除角色「${character.name}」吗？`, '删除确认', {
    type: 'warning',
  })
  await characterStore.removeCharacter(props.projectId, character.id)
}

// AI 润色角色设定
async function polishCharacter() {
  if (!formData.value.name) return

  polishing.value = true
  const content = [
    `【外貌】${formData.value.appearance || '未填写'}`,
    `【性格】${formData.value.personality_traits || '未填写'}`,
    `【背景】${formData.value.background || '未填写'}`,
    `【成长弧线】${formData.value.growth_arc || '未填写'}`,
    `【备注】${formData.value.notes || '未填写'}`,
  ].join('\n\n')

  let result = ''

  streamGenerate(
    props.projectId,
    {
      action: 'polish_character',
      content,
      title: formData.value.name,
      question: roleLabel(formData.value.role_type || 'supporting'),
    },
    (text) => {
      result += text
    },
    () => {
      polishing.value = false
      // 解析 AI 返回的内容，更新表单
      parseAndFillPolishedContent(result)
      ElMessage.success('AI 润色完成')
    },
    (error) => {
      polishing.value = false
      ElMessage.error(`润色失败: ${error}`)
    }
  )
}

// 解析润色后的内容并填充表单
function parseAndFillPolishedContent(text: string) {
  // 尝试解析各个字段
  const sections = text.split(/【[^】]+】/).filter(s => s.trim())
  const labels = text.match(/【([^】]+)】/g) || []

  const fieldMap: Record<string, keyof typeof formData.value> = {
    '外貌': 'appearance',
    '性格': 'personality_traits',
    '背景': 'background',
    '成长弧线': 'growth_arc',
    '成长': 'growth_arc',
    '备注': 'notes',
  }

  labels.forEach((label, index) => {
    const cleanLabel = label.replace(/【|】/g, '')
    const field = fieldMap[cleanLabel]
    if (field && sections[index]) {
      formData.value[field] = sections[index].trim()
    }
  })
}

function resetForm() {
  editingCharacter.value = null
  formData.value = {
    name: '',
    role_type: 'supporting',
    age: '',
    gender: '',
    occupation: '',
    appearance: '',
    personality_traits: '',
    background: '',
    growth_arc: '',
    notes: '',
  }
}

// 监听对话框打开
watch(showEditDialog, (val) => {
  if (!val) resetForm()
})

watch(showCreateDialog, (val) => {
  if (val) {
    resetForm()
    showEditDialog.value = true
  }
})

onMounted(() => {
  characterStore.fetchCharacters(props.projectId)
})
</script>

<style scoped>
.character-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #F7F6F3;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
}

.header-buttons {
  display: flex;
  gap: 8px;
}

.filter-bar {
  padding: 16px 32px;
  background: white;
  border-bottom: 1px solid #f0ede6;
}

:deep(.filter-bar .el-radio-button__inner) {
  background-color: transparent;
  border-color: #E0DFDC;
  color: #5C5C5C;
  border-radius: 8px;
  font-weight: 500;
}

:deep(.filter-bar .el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  border-color: transparent;
  color: white;
}

.ai-analysis-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 32px;
  background: white;
  border-bottom: 1px solid #f0ede6;
}

.analysis-hint {
  font-size: 12px;
  color: #9E9E9E;
}

.analysis-result {
  background: #fefcf7;
  border-bottom: 1px solid #f0ede6;
  max-height: 300px;
  overflow-y: auto;
}

.analysis-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 32px 0;
}

.analysis-title {
  font-size: 13px;
  font-weight: 600;
  color: #5C5C5C;
}

.analysis-content {
  padding: 8px 32px 16px;
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
}

.analysis-content :deep(h3) {
  font-size: 14px;
  margin: 12px 0 4px;
  color: #2C2C2C;
}

.analysis-content :deep(h4) {
  font-size: 13px;
  margin: 8px 0 4px;
  color: #5C5C5C;
}

.character-list {
  flex: 1;
  overflow-y: auto;
  padding: 16px 32px;
}

.character-card {
  display: flex;
  align-items: center;
  padding: 16px;
  margin-bottom: 12px;
  background-color: white;
  border-radius: 14px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #E0DFDC;
  box-shadow: 0 1px 2px rgba(44, 44, 44, 0.03);
}

.character-card:hover {
  box-shadow: 0 4px 12px rgba(107, 123, 141, 0.08);
  border-color: #6B7B8D;
  transform: translateY(-1px);
}

.character-card.active {
  border-color: #6B7B8D;
  box-shadow: 0 0 0 2px rgba(107, 123, 141, 0.12);
}

.avatar-section {
  flex-shrink: 0;
  margin-right: 14px;
}

.info-section {
  flex: 1;
  min-width: 0;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.name {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
}

.meta-row {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #9E9E9E;
}

.meta-row span:not(:last-child)::after {
  content: '·';
  margin-left: 8px;
}

.actions {
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.2s;
}

.character-card:hover .actions {
  opacity: 1;
}

.loading-state,
.empty-state {
  padding: 24px;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-right {
  display: flex;
  gap: 8px;
}

.chapter-select-hint {
  font-size: 13px;
  color: #9E9E9E;
  margin-bottom: 12px;
}

.chapter-select-list {
  max-height: 400px;
  overflow-y: auto;
}

.chapter-select-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0ede6;
}

.chapter-select-item:last-child {
  border-bottom: none;
}

.chapter-select-title {
  font-size: 14px;
  color: #2C2C2C;
}

.chapter-select-words {
  font-size: 12px;
  color: #9E9E9E;
  margin-left: 8px;
}

.chapter-select-empty {
  text-align: center;
  padding: 24px;
  color: #9E9E9E;
  font-size: 13px;
}

.chapter-select-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chapter-select-count {
  font-size: 13px;
  color: #5C5C5C;
}
</style>
