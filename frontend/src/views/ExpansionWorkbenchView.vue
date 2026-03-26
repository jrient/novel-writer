<template>
  <div class="workbench-page">
    <!-- Header -->
    <header class="workbench-header">
      <div class="header-left">
        <el-button text :icon="ArrowLeft" @click="router.push('/expansion')">返回</el-button>
        <span class="project-title">{{ project?.title || '加载中...' }}</span>
        <el-tag :type="statusTagType(project?.status)" size="small">
          {{ statusLabel(project?.status) }}
        </el-tag>
      </div>

      <div class="header-right">
        <el-dropdown trigger="click" @command="handleExport">
          <el-button size="small">
            <el-icon><Download /></el-icon>
            导出
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="txt">导出 TXT</el-dropdown-item>
              <el-dropdown-item command="md">导出 Markdown</el-dropdown-item>
              <el-dropdown-item command="docx">导出 Word</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button size="small" @click="showExportDialog = true">
          <el-icon><Switch /></el-icon>
          导出/转换
        </el-button>
      </div>
    </header>

    <!-- Main three-column layout -->
    <div class="workbench-main">
      <!-- Left: segment list -->
      <aside class="sidebar-left" :style="{ width: leftWidth + 'px' }">
        <ExpansionSegmentList
          :segments="segments"
          :current-segment-id="currentSegmentId"
          :expanding-segment-id="expandingSegmentId"
          @select="handleSelectSegment"
        />
      </aside>

      <!-- Resizer -->
      <div class="resizer" @mousedown="startResizeLeft" />

      <!-- Center: compare panel -->
      <main class="center-column">
        <ExpansionComparePanel
          :original-content="currentSegment?.original_content || ''"
          :expanded-content="currentSegment?.expanded_content || ''"
          :original-word-count="currentSegment?.original_word_count || 0"
          :expanded-word-count="currentSegment?.expanded_word_count ?? null"
          :is-expanding="isCurrentSegmentExpanding"
        />

        <ExpansionProgressBar
          :segments="segments"
          :is-expanding="isExpanding"
          :is-paused="isPaused"
          :expanding-segment-id="expandingSegmentId"
          class="progress-section"
        />
      </main>

      <!-- Resizer -->
      <div class="resizer" @mousedown="startResizeRight" />

      <!-- Right: control panel -->
      <aside class="sidebar-right" :style="{ width: rightWidth + 'px' }">
        <ExpansionControlPanel
          :project-status="project?.status || 'created'"
          :current-segment="currentSegment"
          :is-expanding="isExpanding"
          :is-paused="isPaused"
          :has-pending-segments="hasPendingSegments"
          @update:config="handleConfigUpdate"
          @expand-segment="handleExpandSegment"
          @expand-all="handleExpandAll"
          @pause="handlePause"
          @resume="handleResume"
          @retry="handleRetry"
        />
      </aside>
    </div>

    <!-- Export/Convert Dialog -->
    <el-dialog
      v-model="showExportDialog"
      title="导出与转换"
      width="500px"
    >
      <el-form label-width="80px">
        <el-divider content-position="left">导出</el-divider>

        <el-form-item label="格式">
          <el-radio-group v-model="exportFormat">
            <el-radio value="txt">TXT</el-radio>
            <el-radio value="md">Markdown</el-radio>
            <el-radio value="docx">Word</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="版本">
          <el-radio-group v-model="exportVersion">
            <el-radio value="original">原文</el-radio>
            <el-radio value="expanded">扩写</el-radio>
            <el-radio value="both">两者</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="handleExport(exportFormat)">
            <el-icon><Download /></el-icon>
            下载
          </el-button>
        </el-form-item>

        <el-divider content-position="left">转换</el-divider>

        <el-form-item label="转为">
          <el-radio-group v-model="convertTarget">
            <el-radio value="novel">小说项目</el-radio>
            <el-radio value="drama">剧本项目</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item>
          <el-button type="success" @click="handleConvert">
            <el-icon><Switch /></el-icon>
            创建新项目
          </el-button>
        </el-form-item>
      </el-form>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, Download, Switch } from '@element-plus/icons-vue'
import { useExpansionStore } from '@/stores/expansion'
import ExpansionSegmentList from '@/components/expansion/ExpansionSegmentList.vue'
import ExpansionComparePanel from '@/components/expansion/ExpansionComparePanel.vue'
import ExpansionControlPanel from '@/components/expansion/ExpansionControlPanel.vue'
import ExpansionProgressBar from '@/components/expansion/ExpansionProgressBar.vue'

const route = useRoute()
const router = useRouter()
const expansionStore = useExpansionStore()

const projectId = computed(() => Number(route.params.id))

// State
const pageLoading = ref(true)
const isPaused = ref(false)
const abortController = ref<AbortController | null>(null)

// Layout
const leftWidth = ref(260)
const rightWidth = ref(280)

// Export/Convert
const showExportDialog = ref(false)
const exportFormat = ref<'txt' | 'md' | 'docx'>('txt')
const exportVersion = ref<'original' | 'expanded' | 'both'>('expanded')
const convertTarget = ref<'novel' | 'drama'>('novel')

// Computed
const project = computed(() => expansionStore.currentProject)
const segments = computed(() => expansionStore.segments)
const currentSegmentId = computed(() => expansionStore.currentSegmentId)
const expandingSegmentId = computed(() => expansionStore.expandingSegmentId)
const isExpanding = computed(() => expansionStore.isExpanding)

const currentSegment = computed(() => {
  return segments.value.find(s => s.id === currentSegmentId.value) || null
})

const isCurrentSegmentExpanding = computed(() => {
  return currentSegmentId.value === expandingSegmentId.value
})

const hasPendingSegments = computed(() => {
  return segments.value.some(s => s.status === 'pending')
})

// Methods
function statusTagType(status?: string): 'info' | 'success' | 'warning' | 'danger' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    created: 'info',
    analyzed: 'info',
    segmented: 'warning',
    expanding: 'success',
    paused: 'warning',
    error: 'danger',
    completed: 'success',
  }
  return map[status || ''] || 'info'
}

function statusLabel(status?: string): string {
  const map: Record<string, string> = {
    created: '已创建',
    analyzed: '已分析',
    segmented: '已分段',
    expanding: '扩写中',
    paused: '已暂停',
    error: '出错',
    completed: '已完成',
  }
  return map[status || ''] || status || '未知'
}

async function loadData() {
  pageLoading.value = true
  try {
    await expansionStore.fetchProject(projectId.value)
    await expansionStore.fetchSegments(projectId.value)

    // Select first pending segment
    const firstPending = segments.value.find(s => s.status === 'pending')
    if (firstPending) {
      expansionStore.setCurrentSegment(firstPending.id)
    } else if (segments.value.length > 0) {
      expansionStore.setCurrentSegment(segments.value[0].id)
    }
  } finally {
    pageLoading.value = false
  }
}

function handleSelectSegment(id: number) {
  expansionStore.setCurrentSegment(id)
}

function handleConfigUpdate(config: { expansion_level: string; target_word_count: number | null; style_instructions: string }) {
  expansionStore.updateProject(projectId.value, {
    expansion_level: config.expansion_level as 'light' | 'medium' | 'deep',
    target_word_count: config.target_word_count || undefined,
    style_instructions: config.style_instructions || undefined,
  })
}

function handleExpandSegment(segmentId: number, instructions: string) {
  const segment = segments.value.find(s => s.id === segmentId)
  if (!segment) return

  // Update segment with custom instructions if provided
  if (instructions) {
    expansionStore.editSegment(projectId.value, segmentId, {
      custom_instructions: instructions,
    })
  }

  abortController.value = expansionStore.expandSegment(
    projectId.value,
    segmentId,
    undefined,
    {
      onText: () => {
        // Content is updated in the store
      },
      onDone: () => {
        ElMessage.success('扩写完成')
      },
      onError: (error) => {
        ElMessage.error(error || '扩写失败')
      },
    },
  )
}

function handleExpandAll() {
  isPaused.value = false
  abortController.value = expansionStore.expandProject(projectId.value, {
    onText: () => {},
    onEvent: (type, data) => {
      if (type === 'segment_start') {
        const segId = (data as { segment_id?: number }).segment_id
        if (segId) {
          expansionStore.setCurrentSegment(segId)
        }
      }
    },
    onDone: () => {
      ElMessage.success('全部扩写完成')
    },
    onError: (error) => {
      ElMessage.error(error || '扩写失败')
    },
  })
}

async function handlePause() {
  await expansionStore.pauseExpansionAction(projectId.value)
  isPaused.value = true
  ElMessage.info('已暂停扩写')
}

function handleResume() {
  isPaused.value = false
  abortController.value = expansionStore.resumeExpansion(projectId.value, {
    onText: () => {},
    onEvent: (type, data) => {
      if (type === 'segment_start') {
        const segId = (data as { segment_id?: number }).segment_id
        if (segId) {
          expansionStore.setCurrentSegment(segId)
        }
      }
    },
    onDone: () => {
      ElMessage.success('扩写完成')
    },
    onError: (error) => {
      ElMessage.error(error || '扩写失败')
    },
  })
}

function handleRetry(segmentId: number) {
  abortController.value = expansionStore.retrySegment(projectId.value, segmentId, {
    onText: () => {},
    onDone: () => {
      ElMessage.success('重试成功')
    },
    onError: (error) => {
      ElMessage.error(error || '重试失败')
    },
  })
}

function handleExport(format: string) {
  expansionStore.exportProject(projectId.value, format as 'txt' | 'md' | 'docx', exportVersion.value)
}

async function handleConvert() {
  try {
    const result = await expansionStore.convertProjectAction(projectId.value, convertTarget.value)
    ElMessage.success(`已创建新${convertTarget.value === 'novel' ? '小说' : '剧本'}项目`)
    showExportDialog.value = false

    // Navigate to the new project
    if (convertTarget.value === 'novel') {
      router.push(`/projects/${result.project_id}`)
    } else {
      router.push(`/drama/workbench/${result.project_id}`)
    }
  } catch {
    ElMessage.error('转换失败')
  }
}

// Resizers
function startResizeLeft(e: MouseEvent) {
  const startX = e.clientX
  const startWidth = leftWidth.value

  function onMouseMove(e: MouseEvent) {
    const diff = e.clientX - startX
    leftWidth.value = Math.max(200, Math.min(400, startWidth + diff))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

function startResizeRight(e: MouseEvent) {
  const startX = e.clientX
  const startWidth = rightWidth.value

  function onMouseMove(e: MouseEvent) {
    const diff = startX - e.clientX
    rightWidth.value = Math.max(240, Math.min(400, startWidth + diff))
  }

  function onMouseUp() {
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}

// Lifecycle
onMounted(() => {
  loadData()
})

onUnmounted(() => {
  if (abortController.value) {
    abortController.value.abort()
  }
  expansionStore.clearCurrentProject()
})
</script>

<style scoped>
.workbench-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #ECEAE6;
}

.workbench-header {
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  padding: 0 24px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-title {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
}

.header-right {
  display: flex;
  gap: 8px;
}

.workbench-main {
  flex: 1;
  display: flex;
  min-height: 0;
}

.sidebar-left,
.sidebar-right {
  flex-shrink: 0;
  background: white;
  overflow: hidden;
}

.sidebar-left {
  border-right: 1px solid #E0DFDC;
}

.sidebar-right {
  border-left: 1px solid #E0DFDC;
}

.resizer {
  width: 4px;
  cursor: col-resize;
  background: transparent;
  transition: background 0.2s;
}

.resizer:hover {
  background: #6B7B8D;
}

.center-column {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 16px;
  gap: 16px;
}

.progress-section {
  flex-shrink: 0;
}

@media (max-width: 900px) {
  .workbench-main {
    flex-direction: column;
  }

  .sidebar-left,
  .sidebar-right {
    width: 100% !important;
    max-height: 200px;
    border: none;
    border-bottom: 1px solid #E0DFDC;
  }

  .resizer {
    display: none;
  }
}
</style>