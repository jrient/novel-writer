<template>
  <el-drawer
    v-model="visible"
    title="历史版本"
    direction="rtl"
    size="600px"
    :append-to-body="true"
    class="version-drawer"
  >
    <div class="version-drawer-content">
      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <el-icon class="rotating"><Loading /></el-icon>
        <span>加载中...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="versions.length === 0" class="empty-state">
        <el-icon><Document /></el-icon>
        <p>暂无历史版本</p>
        <span>点击下方按钮手动保存，或编辑内容后自动保存</span>
        <el-button size="small" type="primary" :loading="saving" @click="handleSaveVersion" style="margin-top: 12px">
          保存当前版本
        </el-button>
      </div>

      <!-- 版本列表和对比 -->
      <div v-else class="version-container">
        <!-- 版本列表 -->
        <div class="version-list-section">
          <div class="section-title">
            <span>选择版本</span>
            <el-button size="small" type="primary" text :loading="saving" @click="handleSaveVersion">
              保存当前版本
            </el-button>
          </div>
          <div class="version-list">
            <div
              v-for="version in versions"
              :key="version.id"
              class="version-item"
              :class="{ active: selectedVersion?.id === version.id }"
              @click="selectVersion(version)"
            >
              <div class="version-row">
                <span class="version-number">#{{ version.version_number }}</span>
                <span class="version-words">{{ version.word_count.toLocaleString() }} 字</span>
                <span class="version-time">{{ formatTime(version.created_at) }}</span>
              </div>
              <div v-if="version.change_summary" class="version-summary">
                {{ version.change_summary }}
              </div>
            </div>
          </div>
        </div>

        <!-- 对比面板 -->
        <div v-if="selectedVersion" class="compare-section">
          <div class="compare-header">
            <el-radio-group v-model="compareMode" size="small">
              <el-radio-button label="preview">预览</el-radio-button>
              <el-radio-button label="compare">对比</el-radio-button>
            </el-radio-group>
            <div class="compare-actions">
              <el-button size="small" text @click="copyVersionContent" title="复制版本内容">
                <el-icon><CopyDocument /></el-icon>
              </el-button>
            </div>
          </div>

          <div class="compare-content">
            <div v-if="previewLoading" class="preview-loading">
              <el-icon class="rotating"><Loading /></el-icon>
            </div>
            <template v-else>
              <!-- 预览模式 -->
              <div v-if="compareMode === 'preview'" class="preview-mode">
                <div class="preview-text" @mouseup="handleTextSelect">{{ previewContent }}</div>
              </div>

              <!-- 对比模式 -->
              <div v-else class="compare-mode">
                <div class="compare-column">
                  <div class="column-header">
                    <span>当前版本</span>
                    <span class="word-info">{{ currentContent?.length || 0 }} 字</span>
                  </div>
                  <div class="column-content current" @mouseup="handleTextSelect($event, 'current')">{{ currentContent }}</div>
                </div>
                <div class="compare-divider"></div>
                <div class="compare-column">
                  <div class="column-header">
                    <span>版本 #{{ selectedVersion.version_number }}</span>
                    <span class="word-info">{{ previewContent?.length || 0 }} 字</span>
                  </div>
                  <div class="column-content historical" @mouseup="handleTextSelect($event, 'historical')">{{ previewContent }}</div>
                </div>
              </div>
            </template>
          </div>

          <!-- 选中文本操作 -->
          <div v-if="selectedText" class="selection-panel">
            <div class="selection-info">
              <span>已选中 {{ selectedText.length }} 字</span>
              <el-button size="small" text @click="copySelectedText">
                <el-icon><CopyDocument /></el-icon>
                复制
              </el-button>
              <el-button size="small" text type="primary" @click="adoptSelectedText">
                <el-icon><Position /></el-icon>
                采纳
              </el-button>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="compare-footer">
            <el-button @click="selectedVersion = null">取消选择</el-button>
            <el-button
              type="primary"
              :loading="restoring"
              @click="handleRestore"
            >
              恢复此版本
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Loading, Document, CopyDocument, Position } from '@element-plus/icons-vue'
import {
  getChapterVersions,
  getChapterVersion,
  restoreChapterVersion,
  saveChapterVersion,
  type ChapterVersion,
  type ChapterVersionDetail,
} from '@/api/chapter'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  chapterId: number | null
  currentContent?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'restored': []
  'adopt-text': [text: string]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const versions = ref<ChapterVersion[]>([])
const selectedVersion = ref<ChapterVersion | null>(null)
const previewContent = ref<string>('')
const previewLoading = ref(false)
const restoring = ref(false)
const saving = ref(false)
const compareMode = ref<'preview' | 'compare'>('preview')
const selectedText = ref<string>('')
const selectionSource = ref<'current' | 'historical'>('historical')

// 监听抽屉打开
watch(visible, async (val) => {
  if (val && props.chapterId) {
    await loadVersions()
  } else {
    // 关闭时重置状态
    versions.value = []
    selectedVersion.value = null
    previewContent.value = ''
    selectedText.value = ''
  }
})

// 手动保存当前版本
async function handleSaveVersion() {
  if (!props.chapterId) return
  saving.value = true
  try {
    await saveChapterVersion(props.projectId, props.chapterId)
    ElMessage.success('版本已保存')
    await loadVersions()
  } catch (error: any) {
    ElMessage.error(error?.message || '保存版本失败')
  } finally {
    saving.value = false
  }
}

// 加载版本列表
async function loadVersions() {
  if (!props.chapterId) return
  loading.value = true
  try {
    versions.value = await getChapterVersions(props.projectId, props.chapterId)
  } catch (error) {
    console.error('加载版本列表失败:', error)
    ElMessage.error('加载版本列表失败')
  } finally {
    loading.value = false
  }
}

// 选择版本并加载预览
async function selectVersion(version: ChapterVersion) {
  selectedVersion.value = version
  previewContent.value = ''
  previewLoading.value = true
  selectedText.value = ''

  try {
    const detail: ChapterVersionDetail = await getChapterVersion(
      props.projectId,
      props.chapterId!,
      version.id
    )
    previewContent.value = detail.content
  } catch (error) {
    console.error('加载版本详情失败:', error)
    ElMessage.error('加载版本详情失败')
  } finally {
    previewLoading.value = false
  }
}

// 处理文本选择
function handleTextSelect(_event: MouseEvent, source: 'current' | 'historical' = 'historical') {
  const selection = window.getSelection()
  if (selection && selection.toString().trim()) {
    selectedText.value = selection.toString().trim()
    selectionSource.value = source
  } else {
    selectedText.value = ''
  }
}

// 复制选中文字
function copySelectedText() {
  if (!selectedText.value) return
  navigator.clipboard.writeText(selectedText.value)
  ElMessage.success('已复制到剪贴板')
}

// 采纳选中文字（插入到当前编辑器）
function adoptSelectedText() {
  if (!selectedText.value) return
  emit('adopt-text', selectedText.value)
  ElMessage.success('已采纳选中内容')
}

// 复制整个版本内容
function copyVersionContent() {
  if (!previewContent.value) return
  navigator.clipboard.writeText(previewContent.value)
  ElMessage.success('已复制版本内容')
}

// 恢复版本
async function handleRestore() {
  if (!selectedVersion.value || !props.chapterId) return

  try {
    await ElMessageBox.confirm(
      `确定要恢复到版本 #${selectedVersion.value.version_number} 吗？当前内容会先自动备份。`,
      '恢复确认',
      {
        type: 'warning',
        confirmButtonText: '确认恢复',
        cancelButtonText: '取消',
      }
    )

    restoring.value = true
    const result = await restoreChapterVersion(
      props.projectId,
      props.chapterId,
      selectedVersion.value.id
    )

    ElMessage.success(result.message)
    emit('restored')

    // 重新加载版本列表
    await loadVersions()
    selectedVersion.value = null
    previewContent.value = ''
  } catch (error) {
    if (error !== 'cancel') {
      console.error('恢复版本失败:', error)
      ElMessage.error('恢复版本失败')
    }
  } finally {
    restoring.value = false
  }
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
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`

  return date.toLocaleDateString('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.version-drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: #9E9E9E;
  gap: 8px;
}

.loading-state .el-icon,
.empty-state .el-icon {
  font-size: 32px;
}

.empty-state span {
  font-size: 12px;
  color: #BDBDBD;
}

.version-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.version-list-section {
  flex-shrink: 0;
  max-height: 200px;
  border-bottom: 1px solid #E0DFDC;
}

.section-title {
  font-size: 12px;
  color: #9E9E9E;
  padding: 8px 16px;
  background: #FAFAF8;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.version-list {
  overflow-y: auto;
  max-height: 160px;
}

.version-item {
  padding: 10px 16px;
  border-bottom: 1px solid #f0ede6;
  cursor: pointer;
  transition: background-color 0.15s;
}

.version-item:hover {
  background-color: rgba(107, 123, 141, 0.04);
}

.version-item.active {
  background-color: rgba(107, 123, 141, 0.08);
  border-left: 3px solid #6B7B8D;
  padding-left: 13px;
}

.version-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.version-number {
  font-size: 13px;
  font-weight: 600;
  color: #2C2C2C;
  min-width: 28px;
}

.version-words {
  font-size: 12px;
  color: #5C5C5C;
}

.version-time {
  font-size: 11px;
  color: #9E9E9E;
  margin-left: auto;
}

.version-summary {
  margin-top: 4px;
  font-size: 11px;
  color: #7abf7a;
  background: rgba(122, 191, 122, 0.1);
  padding: 2px 6px;
  border-radius: 3px;
  display: inline-block;
}

/* 对比面板 */
.compare-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.compare-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 16px;
  background: #FAFAF8;
  border-bottom: 1px solid #E0DFDC;
}

.compare-actions {
  display: flex;
  gap: 4px;
}

.compare-content {
  flex: 1;
  overflow: hidden;
  padding: 12px;
}

.preview-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: #9E9E9E;
}

.preview-mode {
  height: 100%;
  overflow-y: auto;
}

.preview-text {
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-all;
  cursor: text;
  user-select: text;
}

/* 对比模式 */
.compare-mode {
  display: flex;
  height: 100%;
  gap: 0;
}

.compare-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #5C5C5C;
  background: #F7F6F3;
  border-radius: 4px 4px 0 0;
}

.word-info {
  color: #9E9E9E;
  font-weight: normal;
}

.column-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-all;
  background: white;
  border: 1px solid #E0DFDC;
  border-top: none;
  border-radius: 0 0 4px 4px;
  cursor: text;
  user-select: text;
}

.column-content.current {
  background: #fafafa;
}

.column-content.historical {
  background: #f0f7ff;
}

.compare-divider {
  width: 12px;
  flex-shrink: 0;
}

/* 选中文本面板 */
.selection-panel {
  padding: 8px 16px;
  background: #e8f4fd;
  border-top: 1px solid #b3d8ff;
}

.selection-info {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
  color: #409eff;
}

/* 操作按钮 */
.compare-footer {
  padding: 12px 16px;
  background: white;
  border-top: 1px solid #E0DFDC;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>