<template>
  <el-drawer
    v-model="visible"
    title="历史版本"
    direction="rtl"
    size="450px"
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
        <span>编辑章节内容后会自动保存版本</span>
      </div>

      <!-- 版本列表 -->
      <div v-else class="version-list">
        <div
          v-for="version in versions"
          :key="version.id"
          class="version-item"
          :class="{ active: selectedVersion?.id === version.id }"
          @click="selectVersion(version)"
        >
          <div class="version-header">
            <span class="version-number">版本 #{{ version.version_number }}</span>
            <span class="version-time">{{ formatTime(version.created_at) }}</span>
          </div>
          <div class="version-info">
            <span class="version-title">{{ version.title }}</span>
            <span class="version-words">{{ version.word_count.toLocaleString() }} 字</span>
          </div>
          <div v-if="version.change_summary" class="version-summary">
            {{ version.change_summary }}
          </div>
        </div>
      </div>
    </div>

    <!-- 预览面板 -->
    <template #footer v-if="selectedVersion">
      <div class="preview-panel">
        <div class="preview-header">
          <span>预览版本 #{{ selectedVersion.version_number }}</span>
          <el-button size="small" text @click="selectedVersion = null">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
        <div class="preview-content" v-if="previewContent">
          <div v-if="previewLoading" class="preview-loading">
            <el-icon class="rotating"><Loading /></el-icon>
          </div>
          <div v-else class="preview-text">{{ previewContent }}</div>
        </div>
        <div class="preview-actions">
          <el-button
            type="primary"
            :loading="restoring"
            @click="handleRestore"
          >
            恢复此版本
          </el-button>
        </div>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Loading, Document, Close } from '@element-plus/icons-vue'
import {
  getChapterVersions,
  getChapterVersion,
  restoreChapterVersion,
  type ChapterVersion,
  type ChapterVersionDetail,
} from '@/api/chapter'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  chapterId: number | null
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'restored': []
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

// 监听抽屉打开
watch(visible, async (val) => {
  if (val && props.chapterId) {
    await loadVersions()
  } else {
    // 关闭时重置状态
    versions.value = []
    selectedVersion.value = null
    previewContent.value = ''
  }
})

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

.version-list {
  flex: 1;
  overflow-y: auto;
}

.version-item {
  padding: 12px 16px;
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

.version-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.version-number {
  font-size: 13px;
  font-weight: 500;
  color: #2C2C2C;
}

.version-time {
  font-size: 11px;
  color: #9E9E9E;
}

.version-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.version-title {
  font-size: 12px;
  color: #5C5C5C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}

.version-words {
  font-size: 11px;
  color: #9E9E9E;
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

/* 预览面板 */
.preview-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  max-height: 300px;
  background: #F7F6F3;
  border-top: 1px solid #E0DFDC;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: #5C5C5C;
  background: white;
  border-bottom: 1px solid #E0DFDC;
}

.preview-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.preview-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100px;
  color: #9E9E9E;
}

.preview-text {
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-all;
}

.preview-actions {
  padding: 12px;
  background: white;
  border-top: 1px solid #E0DFDC;
  display: flex;
  justify-content: center;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>