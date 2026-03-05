<template>
  <div class="worldbuilding-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">世界观设定</span>
      <el-button size="small" type="primary" :icon="Plus" @click="openCreateDialog">
        新建设定
      </el-button>
    </div>

    <!-- 分类筛选 -->
    <div class="category-tabs">
      <el-tag
        v-for="cat in categories"
        :key="cat.value"
        :type="activeCategory === cat.value ? '' : 'info'"
        :effect="activeCategory === cat.value ? 'dark' : 'plain'"
        @click="filterByCategory(cat.value)"
        style="cursor: pointer; margin: 4px"
      >
        {{ cat.label }}
      </el-tag>
    </div>

    <!-- 设定列表 -->
    <div class="entry-list">
      <div v-if="worldbuildingStore.loading" class="loading-state">
        <el-skeleton :rows="2" animated />
      </div>

      <div v-else-if="filteredEntries.length === 0" class="empty-state">
        <el-empty description="暂无设定" :image-size="60" />
      </div>

      <div
        v-else
        v-for="entry in filteredEntries"
        :key="entry.id"
        class="entry-card"
        :class="{ active: currentEntry?.id === entry.id }"
        @click="selectEntry(entry)"
      >
        <div class="entry-header">
          <span class="entry-category" :style="{ borderColor: entry.color || '#e2b714' }">
            {{ categoryLabel(entry.category) }}
          </span>
          <span class="entry-title">{{ entry.title }}</span>
        </div>
        <div v-if="entry.content" class="entry-preview">
          {{ truncate(entry.content, 80) }}
        </div>
        <div v-if="entry.trigger_keywords" class="entry-keywords">
          <el-tag v-for="kw in parseKeywords(entry.trigger_keywords)" :key="kw" size="small" type="info">
            {{ kw }}
          </el-tag>
        </div>
        <div class="entry-actions">
          <el-button text size="small" :icon="Edit" @click.stop="editEntry(entry)" />
          <el-button text size="small" type="danger" :icon="Delete" @click.stop="confirmDelete(entry)" />
        </div>
      </div>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="showEditDialog"
      :title="editingEntry ? '编辑设定' : '新建设定'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="formData" label-width="80px" label-position="left">
        <el-form-item label="标题" required>
          <el-input v-model="formData.title" placeholder="设定标题" />
        </el-form-item>

        <el-form-item label="分类">
          <el-select v-model="formData.category" style="width: 100%">
            <el-option v-for="cat in categories" :key="cat.value" :label="cat.label" :value="cat.value" />
          </el-select>
        </el-form-item>

        <el-form-item label="内容">
          <el-input v-model="formData.content" type="textarea" :rows="6" placeholder="详细描述..." />
        </el-form-item>

        <el-form-item label="触发词">
          <el-input v-model="keywordsInput" placeholder="多个关键词用逗号分隔" />
          <div class="form-tip">在编辑器中输入这些词时会自动提示此设定</div>
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="颜色">
              <el-color-picker v-model="formData.color" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="排序">
              <el-input-number v-model="formData.sort_order" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEntry">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Edit, Delete } from '@element-plus/icons-vue'
import { useWorldbuildingStore } from '@/stores/worldbuilding'
import type { WorldbuildingEntry, CreateWorldbuildingData, UpdateWorldbuildingData } from '@/api/worldbuilding'

const props = defineProps<{
  projectId: number
}>()

const worldbuildingStore = useWorldbuildingStore()

const categories = [
  { value: '地理', label: '地理' },
  { value: '历史', label: '历史' },
  { value: '势力', label: '势力' },
  { value: '魔法体系', label: '魔法体系' },
  { value: '社会制度', label: '社会制度' },
  { value: '文化习俗', label: '文化习俗' },
  { value: '物品', label: '物品' },
  { value: '种族', label: '种族' },
  { value: '其他', label: '其他' },
]

const activeCategory = ref('')
const currentEntry = computed(() => worldbuildingStore.currentEntry)

const filteredEntries = computed(() => {
  if (!activeCategory.value) return worldbuildingStore.entries
  return worldbuildingStore.entries.filter(e => e.category === activeCategory.value)
})

// 对话框状态
const showEditDialog = ref(false)
const editingEntry = ref<WorldbuildingEntry | null>(null)
const saving = ref(false)
const keywordsInput = ref('')

// 表单数据
const formData = ref<CreateWorldbuildingData & UpdateWorldbuildingData>({
  title: '',
  category: '其他',
  content: '',
  trigger_keywords: '',
  sort_order: 0,
  color: '#e2b714',
})

function categoryLabel(cat: string) {
  const found = categories.find(c => c.value === cat)
  return found ? found.label : cat
}

function truncate(text: string, length: number) {
  if (text.length <= length) return text
  return text.slice(0, length) + '...'
}

function parseKeywords(keywords: string | null): string[] {
  if (!keywords) return []
  try {
    return JSON.parse(keywords)
  } catch {
    return keywords.split(',').map(k => k.trim()).filter(Boolean)
  }
}

function filterByCategory(cat: string) {
  activeCategory.value = activeCategory.value === cat ? '' : cat
}

function selectEntry(entry: WorldbuildingEntry) {
  worldbuildingStore.setCurrentEntry(entry)
}

function openCreateDialog() {
  editingEntry.value = null
  formData.value = {
    title: '',
    category: activeCategory.value || '其他',
    content: '',
    trigger_keywords: '',
    sort_order: 0,
    color: '#e2b714',
  }
  keywordsInput.value = ''
  showEditDialog.value = true
}

function editEntry(entry: WorldbuildingEntry) {
  editingEntry.value = entry
  formData.value = {
    title: entry.title,
    category: entry.category,
    content: entry.content || '',
    trigger_keywords: entry.trigger_keywords || '',
    sort_order: entry.sort_order,
    color: entry.color || '#e2b714',
  }
  keywordsInput.value = parseKeywords(entry.trigger_keywords).join(', ')
  showEditDialog.value = true
}

async function saveEntry() {
  if (!formData.value.title) return

  saving.value = true
  try {
    // 处理关键词
    const keywords = keywordsInput.value
      .split(/[,，]/)
      .map(k => k.trim())
      .filter(Boolean)
    formData.value.trigger_keywords = JSON.stringify(keywords)

    if (editingEntry.value) {
      await worldbuildingStore.updateEntry(props.projectId, editingEntry.value.id, formData.value)
    } else {
      await worldbuildingStore.createEntry(props.projectId, formData.value)
    }
    showEditDialog.value = false
  } finally {
    saving.value = false
  }
}

async function confirmDelete(entry: WorldbuildingEntry) {
  await ElMessageBox.confirm(`确定要删除设定「${entry.title}」吗？`, '删除确认', {
    type: 'warning',
  })
  await worldbuildingStore.removeEntry(props.projectId, entry.id)
}

onMounted(() => {
  worldbuildingStore.fetchEntries(props.projectId)
})
</script>

<style scoped>
.worldbuilding-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #16213e;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #2d3561;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2b714;
}

.category-tabs {
  padding: 12px 16px;
  border-bottom: 1px solid #2d3561;
}

.entry-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.entry-card {
  padding: 12px;
  margin-bottom: 8px;
  background-color: rgba(255, 255, 255, 0.03);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
  position: relative;
}

.entry-card:hover {
  background-color: rgba(226, 183, 20, 0.05);
  border-color: #2d3561;
}

.entry-card.active {
  background-color: rgba(226, 183, 20, 0.1);
  border-color: #e2b714;
}

.entry-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.entry-category {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background-color: rgba(255, 255, 255, 0.1);
  color: #909399;
  border-left: 2px solid;
}

.entry-title {
  font-size: 14px;
  font-weight: 600;
  color: #e0e0e0;
}

.entry-preview {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-bottom: 8px;
}

.entry-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.entry-actions {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.entry-card:hover .entry-actions {
  opacity: 1;
}

.loading-state,
.empty-state {
  padding: 24px;
}

.form-tip {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

/* 对话框样式 */
:deep(.el-dialog) {
  background-color: #16213e;
  border: 1px solid #2d3561;
}

:deep(.el-dialog__title) {
  color: #e0e0e0;
}

:deep(.el-form-item__label) {
  color: #c0c4cc;
}

:deep(.el-input__wrapper) {
  background-color: #1a1a2e;
  border-color: #2d3561;
}

:deep(.el-input__inner) {
  color: #e0e0e0;
}

:deep(.el-textarea__inner) {
  background-color: #1a1a2e;
  color: #e0e0e0;
  border-color: #2d3561;
}
</style>