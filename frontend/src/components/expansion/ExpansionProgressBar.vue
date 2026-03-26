<template>
  <div class="progress-bar-container">
    <div class="progress-header">
      <span class="progress-label">扩写进度</span>
      <span class="progress-stats">{{ completedCount }} / {{ totalCount }}</span>
    </div>

    <el-progress
      :percentage="percentage"
      :stroke-width="10"
      :status="progressStatus"
    />

    <div class="progress-info">
      <span v-if="isExpanding" class="status-expanding">
        <el-icon class="is-loading"><Loading /></el-icon>
        正在扩写：{{ currentSegmentName }}
      </span>
      <span v-else-if="isPaused" class="status-paused">
        <el-icon><VideoPause /></el-icon>
        已暂停
      </span>
      <span v-else-if="isCompleted" class="status-completed">
        <el-icon><CircleCheck /></el-icon>
        扩写完成
      </span>
      <span v-else-if="hasError" class="status-error">
        <el-icon><Warning /></el-icon>
        部分段落出错
      </span>
      <span v-else class="status-idle">
        等待开始
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loading, VideoPause, CircleCheck, Warning } from '@element-plus/icons-vue'
import type { ExpansionSegment } from '@/api/expansion'

const props = defineProps<{
  segments: ExpansionSegment[]
  isExpanding: boolean
  isPaused: boolean
  expandingSegmentId: number | null
}>()

const completedCount = computed(() => {
  return props.segments.filter(s => s.status === 'completed').length
})

const totalCount = computed(() => props.segments.length)

const percentage = computed(() => {
  if (totalCount.value === 0) return 0
  return Math.round((completedCount.value / totalCount.value) * 100)
})

const isCompleted = computed(() => {
  return completedCount.value === totalCount.value && totalCount.value > 0
})

const hasError = computed(() => {
  return props.segments.some(s => s.status === 'error')
})

const currentSegmentName = computed(() => {
  const segment = props.segments.find(s => s.id === props.expandingSegmentId)
  return segment?.title || `第${(segment?.sort_order ?? 0) + 1}段`
})

const progressStatus = computed(() => {
  if (isCompleted.value) return 'success'
  if (hasError.value) return 'warning'
  return undefined
})
</script>

<style scoped>
.progress-bar-container {
  padding: 16px;
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.progress-label {
  font-size: 13px;
  font-weight: 500;
  color: #2C2C2C;
}

.progress-stats {
  font-size: 13px;
  color: #6B7B8D;
}

.progress-info {
  margin-top: 8px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.status-expanding {
  color: #6B7B8D;
}

.status-paused {
  color: #E6A23C;
}

.status-completed {
  color: #52C41A;
}

.status-error {
  color: #F56C6C;
}

.status-idle {
  color: #9E9E9E;
}
</style>