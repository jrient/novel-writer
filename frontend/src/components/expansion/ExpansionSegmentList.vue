<template>
  <div class="segment-list">
    <!-- Header stats -->
    <div class="list-header">
      <div class="stats">
        <span class="stat-item">
          <el-icon><Document /></el-icon>
          {{ completedCount }} / {{ segments.length }} 段
        </span>
        <span class="stat-item">
          <el-icon><EditPen /></el-icon>
          {{ totalWordCount.toLocaleString() }} 字
        </span>
      </div>
      <!-- Resegment button -->
      <el-button
        v-if="selectedIds.length >= 2"
        type="primary"
        size="small"
        :loading="isResegmenting"
        @click="handleResegment"
        style="margin-top: 8px; width: 100%"
      >
        <el-icon><Grid /></el-icon>
        再次分段 ({{ selectedIds.length }}段)
      </el-button>
    </div>

    <!-- Segment list -->
    <div class="segment-items">
      <div
        v-for="segment in segments"
        :key="segment.id"
        class="segment-item"
        :class="{
          active: segment.id === currentSegmentId,
          'is-expanding': segment.id === expandingSegmentId,
          selected: selectedIds.includes(segment.id),
        }"
        @click="handleItemClick(segment.id, $event)"
      >
        <!-- Checkbox for multi-select -->
        <el-checkbox
          :model-value="selectedIds.includes(segment.id)"
          @change="(val: boolean) => toggleSelect(segment.id, val)"
          @click.stop
          class="segment-checkbox"
        />

        <div class="segment-status">
          <el-icon v-if="segment.status === 'pending'" class="status-dot"><Loading v-if="segment.id === expandingSegmentId" /><span v-else class="dot" /></el-icon>
          <el-icon v-else-if="segment.status === 'expanding'" class="status-loading is-loading"><Loading /></el-icon>
          <el-icon v-else-if="segment.status === 'completed'" class="status-check"><CircleCheck /></el-icon>
          <el-icon v-else-if="segment.status === 'error'" class="status-error"><Warning /></el-icon>
          <el-icon v-else class="status-skipped"><Minus /></el-icon>
        </div>

        <div class="segment-info">
          <div class="segment-title">
            {{ segment.title || `第${segment.sort_order + 1}段` }}
          </div>
          <div class="segment-meta">
            <span class="word-count">{{ segment.original_word_count }} 字</span>
            <span v-if="segment.expanded_word_count" class="expanded-count">
              → {{ segment.expanded_word_count }} 字
            </span>
          </div>
        </div>

        <el-icon v-if="segment.id === expandingSegmentId" class="expanding-indicator is-loading"><Loading /></el-icon>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Document, EditPen, Loading, CircleCheck, Warning, Minus, Grid } from '@element-plus/icons-vue'
import type { ExpansionSegment } from '@/api/expansion'

const props = defineProps<{
  segments: ExpansionSegment[]
  currentSegmentId: number | null
  expandingSegmentId: number | null
}>()

const emit = defineEmits<{
  select: [segmentId: number]
  resegment: [segmentIds: number[]]
}>()

const selectedIds = ref<number[]>([])
const isResegmenting = ref(false)

const completedCount = computed(() => {
  return props.segments.filter(s => s.status === 'completed').length
})

const totalWordCount = computed(() => {
  return props.segments.reduce((sum, s) => sum + s.original_word_count, 0)
})

function toggleSelect(id: number, selected: boolean) {
  if (selected) {
    if (!selectedIds.value.includes(id)) {
      selectedIds.value.push(id)
    }
  } else {
    selectedIds.value = selectedIds.value.filter(i => i !== id)
  }
}

function handleItemClick(id: number, event: MouseEvent) {
  // Ctrl/Cmd + click for multi-select
  if (event.ctrlKey || event.metaKey) {
    toggleSelect(id, !selectedIds.value.includes(id))
  } else {
    // Normal click: select single and clear multi-selection
    selectedIds.value = []
    emit('select', id)
  }
}

function handleResegment() {
  if (selectedIds.value.length >= 2) {
    emit('resegment', [...selectedIds.value])
    selectedIds.value = []
  }
}

// Expose for parent to control loading state
defineExpose({
  setResegmenting: (val: boolean) => { isResegmenting.value = val }
})
</script>

<style scoped>
.segment-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FAFAFA;
}

.list-header {
  padding: 12px 16px;
  border-bottom: 1px solid #E0DFDC;
  background: white;
}

.stats {
  display: flex;
  gap: 16px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #7A7A7A;
}

.segment-items {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.segment-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 4px;
}

.segment-item:hover {
  background: #F0EFEC;
}

.segment-item.active {
  background: #E8EEF2;
  border: 1px solid #6B7B8D;
}

.segment-item.is-expanding {
  background: #FFF8E6;
}

.segment-item.selected {
  background: #E6F7FF;
  border: 1px solid #1890FF;
}

.segment-checkbox {
  flex-shrink: 0;
}

.segment-status {
  width: 20px;
  display: flex;
  justify-content: center;
}

.status-dot .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #D9D9D9;
  display: inline-block;
}

.status-loading {
  color: #6B7B8D;
}

.status-check {
  color: #52C41A;
}

.status-error {
  color: #F56C6C;
}

.status-skipped {
  color: #9E9E9E;
}

.segment-info {
  flex: 1;
  min-width: 0;
}

.segment-title {
  font-size: 13px;
  font-weight: 500;
  color: #2C2C2C;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.segment-meta {
  font-size: 11px;
  color: #9E9E9E;
  margin-top: 2px;
}

.word-count {
  margin-right: 4px;
}

.expanded-count {
  color: #52C41A;
}

.expanding-indicator {
  color: #6B7B8D;
}
</style>