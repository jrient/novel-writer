<template>
  <el-drawer
    v-model="visible"
    title="妙记"
    direction="rtl"
    size="400px"
    :append-to-body="true"
    class="miaoji-drawer"
    @close="handleClose"
  >
    <div class="miaoji-container">
      <!-- 编辑区域 -->
      <div class="editor-section">
        <el-input
          v-model="currentContent"
          type="textarea"
          :rows="8"
          placeholder="随时记录你的灵感..."
          @input="handleAutoSave"
          class="miaoji-input"
        />
        <div class="editor-actions">
          <el-button type="primary" size="small" @click="handleSave" :loading="saving">
            保存
          </el-button>
        </div>
      </div>

      <!-- 妙记列表 -->
      <div class="list-section">
        <div class="list-header">
          <span>历史妙记</span>
          <span class="count">{{ miaojiList.length }} 条</span>
        </div>

        <div v-if="loading" class="loading-state">
          <el-icon class="rotating"><Loading /></el-icon>
        </div>

        <div v-else-if="miaojiList.length === 0" class="empty-state">
          暂无妙记
        </div>

        <div v-else class="miaoji-list">
          <div
            v-for="item in miaojiList"
            :key="item.id"
            class="miaoji-item"
            :class="{ active: selectedNote?.id === item.id }"
            @click="selectNote(item)"
          >
            <div class="item-header">
              <span class="item-title">{{ item.title }}</span>
              <span class="item-time">{{ formatTime(item.created_at) }}</span>
            </div>
            <div class="item-preview">{{ getPreview(item.content) }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 详情对话框 -->
    <el-dialog
      v-model="showDetail"
      title="妙记详情"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-input
        v-model="editingContent"
        type="textarea"
        :rows="12"
        placeholder="妙记内容..."
      />
      <template #footer>
        <div class="detail-footer">
          <el-button type="warning" :loading="parsing" @click="handleParse">
            <el-icon><MagicStick /></el-icon>
            解析应用
          </el-button>
          <div class="footer-right">
            <el-button type="danger" text @click="handleDelete">
              <el-icon><Delete /></el-icon>
            </el-button>
            <el-button @click="showDetail = false">取消</el-button>
            <el-button type="primary" :loading="saving" @click="handleUpdate">
              保存
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 解析结果对话框 -->
    <el-dialog
      v-model="showParseResult"
      title="解析结果"
      width="600px"
    >
      <div v-if="parseResult" class="parse-result">
        <el-alert
          :title="parseResult.summary"
          type="success"
          :closable="false"
          show-icon
          class="parse-summary"
        />

        <div v-if="parseResult.characters.length > 0" class="result-section">
          <h4>角色 ({{ parseResult.characters.length }})</h4>
          <el-tag v-for="c in parseResult.characters" :key="c.name" class="result-tag">
            {{ c.name }}
          </el-tag>
        </div>

        <div v-if="parseResult.worldbuilding.length > 0" class="result-section">
          <h4>设定 ({{ parseResult.worldbuilding.length }})</h4>
          <el-tag v-for="w in parseResult.worldbuilding" :key="w.name" type="info" class="result-tag">
            {{ w.name }}
          </el-tag>
        </div>

        <div v-if="parseResult.outline.length > 0" class="result-section">
          <h4>大纲 ({{ parseResult.outline.length }})</h4>
          <el-tag v-for="o in parseResult.outline" :key="o.title" type="success" class="result-tag">
            {{ o.title }}
          </el-tag>
        </div>

        <div v-if="parseResult.events.length > 0" class="result-section">
          <h4>事件 ({{ parseResult.events.length }})</h4>
          <el-tag v-for="e in parseResult.events" :key="e.title" type="warning" class="result-tag">
            {{ e.title }}
          </el-tag>
        </div>
      </div>
    </el-dialog>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Loading, MagicStick, Delete } from '@element-plus/icons-vue'
import {
  getNotes,
  createNote,
  updateNote,
  deleteNote,
  parseMiaoji,
  type Note,
  type MiaojiParseResult,
} from '@/api/note'

const props = defineProps<{
  modelValue: boolean
  projectId: number
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'parsed': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const saving = ref(false)
const parsing = ref(false)
const miaojiList = ref<Note[]>([])
const currentContent = ref('')
const selectedNote = ref<Note | null>(null)
const editingContent = ref('')
const showDetail = ref(false)
const showParseResult = ref(false)
const parseResult = ref<MiaojiParseResult | null>(null)

let autoSaveTimer: ReturnType<typeof setTimeout> | null = null

// 监听打开
watch(visible, (val) => {
  if (val) {
    loadMiaojiList()
  }
})

// 加载妙记列表
async function loadMiaojiList() {
  loading.value = true
  try {
    miaojiList.value = await getNotes(props.projectId, 'miaoji')
  } catch (error) {
    console.error('加载妙记失败:', error)
  } finally {
    loading.value = false
  }
}

// 自动保存（防抖）
function handleAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    if (currentContent.value.trim()) {
      handleQuickSave()
    }
  }, 2000)
}

// 快速保存
async function handleQuickSave() {
  if (!currentContent.value.trim()) return

  saving.value = true
  try {
    const note = await createNote(props.projectId, {
      title: currentContent.value.slice(0, 20) + (currentContent.value.length > 20 ? '...' : ''),
      content: currentContent.value,
      note_type: 'miaoji',
    })
    miaojiList.value.unshift(note)
    currentContent.value = ''
    ElMessage.success('妙记已保存')
  } catch (error) {
    console.error('保存失败:', error)
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 手动保存
async function handleSave() {
  if (!currentContent.value.trim()) {
    ElMessage.warning('请输入内容')
    return
  }
  await handleQuickSave()
}

// 选择笔记
function selectNote(note: Note) {
  selectedNote.value = note
  editingContent.value = note.content || ''
  showDetail.value = true
}

// 更新笔记
async function handleUpdate() {
  if (!selectedNote.value) return

  saving.value = true
  try {
    const updated = await updateNote(props.projectId, selectedNote.value.id, {
      content: editingContent.value,
      title: editingContent.value.slice(0, 20) + (editingContent.value.length > 20 ? '...' : ''),
    })
    const index = miaojiList.value.findIndex(n => n.id === updated.id)
    if (index >= 0) {
      miaojiList.value[index] = updated
    }
    showDetail.value = false
    ElMessage.success('更新成功')
  } catch (error) {
    console.error('更新失败:', error)
    ElMessage.error('更新失败')
  } finally {
    saving.value = false
  }
}

// 删除笔记
async function handleDelete() {
  if (!selectedNote.value) return

  try {
    await ElMessageBox.confirm('确定删除这条妙记吗？', '删除确认', { type: 'warning' })
    await deleteNote(props.projectId, selectedNote.value.id)
    miaojiList.value = miaojiList.value.filter(n => n.id !== selectedNote.value?.id)
    showDetail.value = false
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
    }
  }
}

// 解析妙记
async function handleParse() {
  if (!selectedNote.value) return

  parsing.value = true
  try {
    parseResult.value = await parseMiaoji(props.projectId, selectedNote.value.id)
    showParseResult.value = true
    emit('parsed')
    ElMessage.success('解析完成，已自动添加到对应分区')
  } catch (error) {
    console.error('解析失败:', error)
    ElMessage.error('解析失败')
  } finally {
    parsing.value = false
  }
}

// 关闭时清理
function handleClose() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  if (currentContent.value.trim()) {
    handleQuickSave()
  }
}

// 获取预览文本
function getPreview(content: string | null): string {
  if (!content) return ''
  return content.length > 50 ? content.slice(0, 50) + '...' : content
}

// 格式化时间
function formatTime(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes}分钟前`
  if (hours < 24) return `${hours}小时前`
  if (days < 7) return `${days}天前`

  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}
</script>

<style scoped>
.miaoji-container {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.editor-section {
  padding: 16px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
}

.miaoji-input :deep(.el-textarea__inner) {
  background: #F7F6F3;
  border-color: #E0DFDC;
  font-size: 14px;
  line-height: 1.8;
}

.editor-actions {
  margin-top: 8px;
  text-align: right;
}

.list-section {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-size: 13px;
  color: #5C5C5C;
}

.count {
  color: #9E9E9E;
}

.loading-state,
.empty-state {
  text-align: center;
  padding: 40px;
  color: #9E9E9E;
}

.miaoji-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.miaoji-item {
  padding: 12px;
  background: white;
  border-radius: 8px;
  border: 1px solid #E0DFDC;
  cursor: pointer;
  transition: all 0.2s;
}

.miaoji-item:hover {
  border-color: #6B7B8D;
}

.miaoji-item.active {
  border-color: #6B7B8D;
  background: rgba(107, 123, 141, 0.05);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.item-title {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
}

.item-time {
  font-size: 11px;
  color: #9E9E9E;
}

.item-preview {
  font-size: 12px;
  color: #7A7A7A;
  line-height: 1.5;
}

.detail-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.footer-right {
  display: flex;
  gap: 8px;
}

.parse-result {
  padding: 16px;
}

.parse-summary {
  margin-bottom: 16px;
}

.result-section {
  margin-bottom: 16px;
}

.result-section h4 {
  font-size: 13px;
  color: #5C5C5C;
  margin-bottom: 8px;
}

.result-tag {
  margin-right: 8px;
  margin-bottom: 8px;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 手机端适配 */
@media (max-width: 768px) {
  .miaoji-drawer :deep(.el-drawer__body) {
    padding: 0;
  }

  .editor-section {
    padding: 12px;
  }

  .list-section {
    padding: 12px;
  }
}
</style>