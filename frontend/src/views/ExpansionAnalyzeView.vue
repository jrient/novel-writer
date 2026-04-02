<template>
  <div class="expansion-analyze-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.push('/expansion')">返回列表</el-button>
          <h1 class="page-title">{{ project?.title || '文本分析' }}</h1>
        </div>
        <div class="header-right">
          <el-tag :type="statusTagType(project?.status)" size="small">
            {{ statusLabel(project?.status) }}
          </el-tag>
        </div>
      </div>
    </header>

    <!-- Loading -->
    <div v-if="pageLoading" class="page-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- Main content -->
    <main v-else class="page-main">
      <div class="analyze-layout">
        <!-- Left: Main content area -->
        <div class="main-area">
          <!-- Summary section -->
          <el-card class="summary-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span class="header-title">内容摘要</span>
                <el-button
                  v-if="project?.summary && !analyzing"
                  text
                  size="small"
                  :icon="Edit"
                  @click="editingSummary = true"
                >
                  编辑
                </el-button>
              </div>
            </template>

            <!-- Analyzing state -->
            <div v-if="analyzing" class="analyzing-area">
              <div class="stream-output">
                <div v-if="streamingSummary" class="streaming-text">
                  {{ streamingSummary }}
                  <span class="cursor-blink">|</span>
                </div>
                <div v-else class="waiting-text">
                  <el-icon class="is-loading"><Loading /></el-icon>
                  {{ analysisPhase || 'AI 正在分析文本...' }}
                </div>
              </div>
            </div>

            <!-- Edit mode -->
            <div v-else-if="editingSummary" class="summary-edit">
              <el-input
                v-model="editedSummary"
                type="textarea"
                :rows="6"
                placeholder="请输入摘要内容"
              />
              <div class="edit-actions">
                <el-button size="small" @click="editingSummary = false">取消</el-button>
                <el-button size="small" type="primary" @click="saveSummary">保存</el-button>
              </div>
            </div>

            <!-- Display mode -->
            <div v-else-if="project?.summary" class="summary-display">
              {{ project.summary }}
            </div>

            <!-- Empty state -->
            <div v-else class="summary-empty">
              <el-empty description="点击开始分析按钮进行文本分析" :image-size="60" />
              <el-button
                v-if="project?.status === 'created'"
                type="primary"
                :loading="analyzing"
                @click="startAnalysis"
              >
                开始分析
              </el-button>
            </div>
          </el-card>

          <!-- Style profile section -->
          <StyleProfileCard
            :profile="project?.style_profile ?? null"
            :loading="analyzing"
            class="style-card"
          />

          <!-- Segments section -->
          <el-card class="segments-card" shadow="never">
            <template #header>
              <div class="card-header">
                <span class="header-title">分段列表</span>
                <div class="header-actions">
                  <el-button
                    v-if="segments.length > 0"
                    text
                    size="small"
                    :loading="analyzing"
                    @click="startResegment"
                  >
                    重新分段
                  </el-button>
                  <el-tag size="small" type="info">
                    共 {{ segments.length }} 段 / {{ totalWordCount.toLocaleString() }} 字
                  </el-tag>
                </div>
              </div>
            </template>

            <el-table
              v-if="segments.length > 0"
              :data="segments"
              stripe
              size="small"
            >
              <el-table-column prop="sort_order" label="序号" width="60" align="center">
                <template #default="{ row }">
                  {{ row.sort_order + 1 }}
                </template>
              </el-table-column>
              <el-table-column prop="title" label="标题" min-width="150">
                <template #default="{ row }">
                  {{ row.title || `第${row.sort_order + 1}段` }}
                </template>
              </el-table-column>
              <el-table-column prop="original_word_count" label="字数" width="80" align="right">
                <template #default="{ row }">
                  {{ row.original_word_count.toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column prop="expansion_level" label="扩写深度" width="90" align="center">
                <template #default="{ row }">
                  <el-tag size="small" effect="plain">
                    {{ levelLabel(row.expansion_level || project?.expansion_level) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="status" label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="segmentStatusTagType(row.status)" size="small">
                    {{ segmentStatusLabel(row.status) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="160" align="center">
                <template #default="{ row }">
                  <el-button text size="small" @click="openSplitDialog(row)">拆分</el-button>
                  <el-button text size="small" @click="openMergeDialog(row)">合并</el-button>
                  <el-button text size="small" @click="editSegmentTitle(row)">编辑</el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-empty v-else description="暂无分段数据" :image-size="60" />
          </el-card>
        </div>

        <!-- Right: Config sidebar -->
        <div class="config-sidebar">
          <el-card class="config-card" shadow="never">
            <template #header>
              <span class="header-title">扩写配置</span>
            </template>

            <el-form label-position="top" size="small">
              <el-form-item label="扩写深度">
                <el-radio-group v-model="configForm.expansion_level" @change="updateConfig">
                  <el-radio-button value="light">轻度</el-radio-button>
                  <el-radio-button value="medium">中度</el-radio-button>
                  <el-radio-button value="deep">深度</el-radio-button>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="目标字数">
                <el-input-number
                  v-model="configForm.target_word_count"
                  :min="0"
                  :max="200000"
                  :step="1000"
                  style="width: 100%"
                  @change="updateConfig"
                />
              </el-form-item>

              <el-form-item label="执行模式">
                <el-radio-group v-model="configForm.execution_mode" @change="updateConfig">
                  <el-radio-button value="auto">自动扩写</el-radio-button>
                  <el-radio-button value="step_by_step">逐步确认</el-radio-button>
                </el-radio-group>
              </el-form-item>

              <el-form-item label="风格指导">
                <el-input
                  v-model="configForm.style_instructions"
                  type="textarea"
                  :rows="3"
                  placeholder="输入额外的风格指导..."
                  @change="updateConfig"
                />
              </el-form-item>
            </el-form>
          </el-card>

          <!-- Action buttons -->
          <div class="action-buttons">
            <el-button
              v-if="canStartExpansion"
              type="primary"
              size="large"
              :icon="VideoPlay"
              @click="goToWorkbench"
              round
            >
              开始扩写
            </el-button>
            <el-button
              v-else-if="project?.status === 'created'"
              type="primary"
              size="large"
              :loading="analyzing"
              @click="startAnalysis"
              round
            >
              开始分析
            </el-button>
          </div>
        </div>
      </div>
    </main>

    <!-- Split/Merge Dialog -->
    <SegmentSplitDialog
      v-model="showSplitMergeDialog"
      :mode="splitMergeMode"
      :segment="selectedSegment"
      :adjacent-segments="adjacentSegments"
      @split="handleSplit"
      @merge="handleMerge"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Edit, Loading, VideoPlay } from '@element-plus/icons-vue'
import { useExpansionStore } from '@/stores/expansion'
import StyleProfileCard from '@/components/expansion/StyleProfileCard.vue'
import SegmentSplitDialog from '@/components/expansion/SegmentSplitDialog.vue'
import type { ExpansionSegment } from '@/api/expansion'

const route = useRoute()
const router = useRouter()
const expansionStore = useExpansionStore()

const projectId = computed(() => Number(route.params.id))

// State
const pageLoading = ref(true)
const analyzing = ref(false)
const streamingSummary = ref('')
const analysisPhase = ref('')  // 当前分析阶段提示
const editingSummary = ref(false)
const editedSummary = ref('')
const abortController = ref<AbortController | null>(null)

// Project & Segments
const project = computed(() => expansionStore.currentProject)
const segments = computed(() => expansionStore.segments)

const totalWordCount = computed(() => {
  return segments.value.reduce((sum, s) => sum + s.original_word_count, 0)
})

// Config form
const configForm = ref({
  expansion_level: 'medium' as 'light' | 'medium' | 'deep',
  target_word_count: null as number | null,
  execution_mode: 'auto' as 'auto' | 'step_by_step',
  style_instructions: '',
})

// Split/Merge dialog
const showSplitMergeDialog = ref(false)
const splitMergeMode = ref<'split' | 'merge'>('split')
const selectedSegment = ref<ExpansionSegment | null>(null)
const adjacentSegments = ref<ExpansionSegment[]>([])

// Computed
const canStartExpansion = computed(() => {
  return project.value?.status && ['analyzed', 'segmented', 'expanding', 'paused', 'error', 'completed'].includes(project.value.status)
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

function levelLabel(level?: string): string {
  const map: Record<string, string> = {
    light: '轻度',
    medium: '中度',
    deep: '深度',
  }
  return map[level || ''] || '中度'
}

function segmentStatusTagType(status: string): 'info' | 'success' | 'warning' | 'danger' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    pending: 'info',
    expanding: 'success',
    completed: 'success',
    error: 'danger',
    skipped: 'warning',
  }
  return map[status] || 'info'
}

function segmentStatusLabel(status: string): string {
  const map: Record<string, string> = {
    pending: '待扩写',
    expanding: '扩写中',
    completed: '已完成',
    error: '出错',
    skipped: '已跳过',
  }
  return map[status] || status
}

async function loadData() {
  pageLoading.value = true
  try {
    await expansionStore.fetchProject(projectId.value)
    await expansionStore.fetchSegments(projectId.value)

    // Sync config form
    if (project.value) {
      configForm.value = {
        expansion_level: project.value.expansion_level,
        target_word_count: project.value.target_word_count,
        execution_mode: project.value.execution_mode,
        style_instructions: project.value.style_instructions || '',
      }
    }
  } finally {
    pageLoading.value = false
  }
}

function startAnalysis() {
  analyzing.value = true
  streamingSummary.value = ''
  analysisPhase.value = '正在识别自然断点...'

  abortController.value = expansionStore.startAnalysis(projectId.value, {
    onText: (text) => {
      streamingSummary.value += text
    },
    onEvent: (type, data) => {
      if (type === 'phase') {
        const phaseData = data as { phase?: string; message?: string }
        analysisPhase.value = phaseData.message || ''
      }
    },
    onDone: () => {
      analyzing.value = false
      analysisPhase.value = ''
      ElMessage.success('分析完成')
      // 刷新项目和分段数据
      expansionStore.fetchProject(projectId.value)
      expansionStore.fetchSegments(projectId.value)
    },
    onError: (error) => {
      analyzing.value = false
      analysisPhase.value = ''
      ElMessage.error(error || '分析失败')
    },
  })
}

function startResegment() {
  analyzing.value = true
  streamingSummary.value = ''
  analysisPhase.value = '正在重新识别自然断点...'

  abortController.value = expansionStore.resegment(projectId.value, {
    onText: (text) => {
      streamingSummary.value += text
    },
    onEvent: (type, data) => {
      if (type === 'phase') {
        const phaseData = data as { phase?: string; message?: string }
        analysisPhase.value = phaseData.message || ''
      }
    },
    onDone: () => {
      analyzing.value = false
      analysisPhase.value = ''
      ElMessage.success('重新分段完成')
      // 刷新项目和分段数据
      expansionStore.fetchProject(projectId.value)
      expansionStore.fetchSegments(projectId.value)
    },
    onError: (error) => {
      analyzing.value = false
      analysisPhase.value = ''
      ElMessage.error(error || '重新分段失败')
    },
  })
}

async function saveSummary() {
  if (!project.value) return

  try {
    await expansionStore.updateProject(project.value.id, {
      summary: editedSummary.value,
    })
    editingSummary.value = false
    ElMessage.success('摘要已更新')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function updateConfig() {
  if (!project.value) return

  try {
    await expansionStore.updateProject(project.value.id, {
      expansion_level: configForm.value.expansion_level,
      target_word_count: configForm.value.target_word_count || undefined,
      execution_mode: configForm.value.execution_mode,
      style_instructions: configForm.value.style_instructions || undefined,
    })
    ElMessage.success('配置已更新')
  } catch {
    ElMessage.error('更新失败')
  }
}

function openSplitDialog(segment: ExpansionSegment) {
  splitMergeMode.value = 'split'
  selectedSegment.value = segment
  adjacentSegments.value = []
  showSplitMergeDialog.value = true
}

function openMergeDialog(segment: ExpansionSegment) {
  splitMergeMode.value = 'merge'
  selectedSegment.value = segment
  // Get adjacent segments (before and after)
  const idx = segments.value.findIndex(s => s.id === segment.id)
  adjacentSegments.value = segments.value.slice(Math.max(0, idx - 1), idx + 2)
  showSplitMergeDialog.value = true
}

async function handleSplit(segmentId: number, splitPosition: number) {
  try {
    await expansionStore.splitSegmentAction(projectId.value, {
      segment_id: segmentId,
      split_position: splitPosition,
    })
    ElMessage.success('拆分成功')
  } catch {
    ElMessage.error('拆分失败')
  }
}

async function handleMerge(segmentIds: number[]) {
  try {
    await expansionStore.mergeSegmentsAction(projectId.value, {
      segment_ids: segmentIds,
    })
    ElMessage.success('合并成功')
  } catch {
    ElMessage.error('合并失败')
  }
}

async function editSegmentTitle(segment: ExpansionSegment) {
  try {
    const { value } = await ElMessageBox.prompt('请输入段落标题', '编辑标题', {
      inputValue: segment.title || '',
      inputPlaceholder: '段落标题',
    })
    if (value !== null) {
      await expansionStore.editSegment(projectId.value, segment.id, {
        title: value,
      })
      ElMessage.success('标题已更新')
    }
  } catch {
    // Cancelled
  }
}

function goToWorkbench() {
  router.push(`/expansion/workbench/${projectId.value}`)
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
.expansion-analyze-page {
  min-height: 100vh;
  background-color: #F0EFEC;
}

.page-header {
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  box-shadow: 0 1px 3px rgba(44, 44, 44, 0.03);
}

.header-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
  font-family: 'Noto Serif SC', serif;
}

.page-loading {
  max-width: 1200px;
  margin: 32px auto;
  padding: 24px;
  background: white;
  border-radius: 14px;
}

.page-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

.analyze-layout {
  display: flex;
  gap: 24px;
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.config-sidebar {
  width: 280px;
  flex-shrink: 0;
}

.summary-card,
.style-card,
.segments-card,
.config-card {
  border: 1px solid #E0DFDC;
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
}

.analyzing-area {
  min-height: 120px;
}

.stream-output {
  font-size: 14px;
  line-height: 1.8;
  color: #5C5C5C;
}

.streaming-text {
  white-space: pre-wrap;
}

.cursor-blink {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.waiting-text {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #9E9E9E;
}

.summary-edit {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.summary-display {
  font-size: 14px;
  line-height: 1.8;
  color: #5C5C5C;
  white-space: pre-wrap;
}

.summary-empty {
  padding: 20px 0;
  text-align: center;
}

.config-card {
  position: sticky;
  top: 32px;
}

.action-buttons {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.action-buttons .el-button {
  width: 100%;
}

@media (max-width: 900px) {
  .analyze-layout {
    flex-direction: column;
  }

  .config-sidebar {
    width: 100%;
  }

  .page-main { padding: 16px; }
  .page-header { padding: 0 16px; }
}
</style>