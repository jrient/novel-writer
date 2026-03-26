<template>
  <el-dialog
    v-model="visible"
    :title="mode === 'split' ? '拆分段落' : '合并段落'"
    width="700px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- Split mode -->
    <div v-if="mode === 'split'" class="split-content">
      <div class="segment-info">
        <span class="label">当前段落：</span>
        <span class="title">{{ segment?.title || '无标题' }}</span>
        <span class="word-count">({{ segment?.original_word_count || 0 }} 字)</span>
      </div>

      <div class="split-instruction">
        点击文本选择拆分位置，将在此处分割成两段
      </div>

      <div
        ref="textContainerRef"
        class="text-container"
        @click="handleTextClick"
      >
        <span
          v-for="(char, idx) in textChars"
          :key="idx"
          :class="{ 'cursor-position': idx === splitPosition }"
          class="text-char"
        >
          {{ char }}
        </span>
      </div>

      <div v-if="splitPosition !== null" class="split-preview">
        <div class="preview-item">
          <span class="preview-label">前半段：</span>
          <span>{{ segment?.original_content.slice(0, splitPosition).length }} 字</span>
        </div>
        <div class="preview-item">
          <span class="preview-label">后半段：</span>
          <span>{{ segment?.original_content.slice(splitPosition).length }} 字</span>
        </div>
      </div>
    </div>

    <!-- Merge mode -->
    <div v-else class="merge-content">
      <div class="merge-instruction">
        选择相邻段落进行合并，合并后内容将按顺序拼接
      </div>

      <div class="segment-list">
        <div
          v-for="seg in adjacentSegments"
          :key="seg.id"
          class="segment-item"
          :class="{ selected: selectedSegmentIds.includes(seg.id) }"
          @click="toggleSegmentSelection(seg.id)"
        >
          <el-checkbox :model-value="selectedSegmentIds.includes(seg.id)" />
          <div class="segment-info">
            <span class="segment-order">第{{ seg.sort_order + 1 }}段</span>
            <span class="segment-title">{{ seg.title || '无标题' }}</span>
            <span class="segment-words">({{ seg.original_word_count }} 字)</span>
          </div>
        </div>
      </div>

      <div v-if="selectedSegmentIds.length > 1" class="merge-preview">
        合并后将生成 {{ selectedSegmentIds.length }} 段内容，共
        {{ totalMergeWordCount }} 字
      </div>
    </div>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button
        type="primary"
        :disabled="!canConfirm"
        :loading="loading"
        @click="handleConfirm"
      >
        确认{{ mode === 'split' ? '拆分' : '合并' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ExpansionSegment } from '@/api/expansion'

const props = defineProps<{
  modelValue: boolean
  mode: 'split' | 'merge'
  segment: ExpansionSegment | null
  adjacentSegments: ExpansionSegment[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'split': [segmentId: number, splitPosition: number]
  'merge': [segmentIds: number[]]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const loading = ref(false)
const splitPosition = ref<number | null>(null)
const selectedSegmentIds = ref<number[]>([])

// Split mode
const textChars = computed(() => {
  if (!props.segment) return []
  return props.segment.original_content.split('')
})

function handleTextClick(event: MouseEvent) {
  const target = event.target as HTMLElement
  if (target.classList.contains('text-char')) {
    const container = target.parentElement
    if (!container) return
    const chars = container.querySelectorAll('.text-char')
    const idx = Array.from(chars).indexOf(target)
    if (idx !== -1) {
      splitPosition.value = idx
    }
  }
}

// Merge mode
function toggleSegmentSelection(segId: number) {
  const idx = selectedSegmentIds.value.indexOf(segId)
  if (idx === -1) {
    selectedSegmentIds.value.push(segId)
    // Sort by sort_order
    selectedSegmentIds.value.sort((a, b) => {
      const segA = props.adjacentSegments.find(s => s.id === a)
      const segB = props.adjacentSegments.find(s => s.id === b)
      return (segA?.sort_order || 0) - (segB?.sort_order || 0)
    })
  } else {
    selectedSegmentIds.value.splice(idx, 1)
  }
}

const totalMergeWordCount = computed(() => {
  return props.adjacentSegments
    .filter(s => selectedSegmentIds.value.includes(s.id))
    .reduce((sum, s) => sum + s.original_word_count, 0)
})

// Validation
const canConfirm = computed(() => {
  if (props.mode === 'split') {
    return splitPosition.value !== null && splitPosition.value > 0
  }
  return selectedSegmentIds.value.length >= 2
})

// Actions
async function handleConfirm() {
  loading.value = true
  try {
    if (props.mode === 'split' && props.segment && splitPosition.value !== null) {
      emit('split', props.segment.id, splitPosition.value)
    } else if (props.mode === 'merge' && selectedSegmentIds.value.length >= 2) {
      emit('merge', selectedSegmentIds.value)
    }
    handleClose()
  } finally {
    loading.value = false
  }
}

function handleClose() {
  visible.value = false
  splitPosition.value = null
  selectedSegmentIds.value = []
}

// Reset state when dialog opens
watch(visible, (val) => {
  if (val) {
    splitPosition.value = null
    selectedSegmentIds.value = []
  }
})
</script>

<style scoped>
.split-content,
.merge-content {
  min-height: 300px;
}

.segment-info {
  margin-bottom: 12px;
}

.segment-info .label {
  color: #9E9E9E;
}

.segment-info .title {
  font-weight: 500;
  color: #2C2C2C;
}

.segment-info .word-count {
  color: #9E9E9E;
  font-size: 12px;
}

.split-instruction,
.merge-instruction {
  font-size: 13px;
  color: #7A7A7A;
  margin-bottom: 12px;
}

.text-container {
  max-height: 300px;
  overflow-y: auto;
  padding: 12px;
  background: #FAFAFA;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  line-height: 1.8;
  cursor: pointer;
  font-size: 14px;
}

.text-char {
  position: relative;
}

.text-char.cursor-position {
  background: #6B7B8D;
  color: white;
}

.text-char.cursor-position::before {
  content: '|';
  position: absolute;
  left: -1px;
  color: #6B7B8D;
}

.split-preview {
  display: flex;
  gap: 24px;
  margin-top: 12px;
  padding: 12px;
  background: #F5F5F5;
  border-radius: 8px;
}

.preview-item {
  font-size: 13px;
}

.preview-label {
  color: #9E9E9E;
  margin-right: 8px;
}

.segment-list {
  max-height: 400px;
  overflow-y: auto;
}

.segment-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.segment-item:hover {
  border-color: #6B7B8D;
}

.segment-item.selected {
  border-color: #6B7B8D;
  background: #F5F5F5;
}

.segment-item .segment-info {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
}

.segment-order {
  font-size: 12px;
  color: #9E9E9E;
}

.segment-title {
  font-weight: 500;
  color: #2C2C2C;
}

.segment-words {
  font-size: 12px;
  color: #9E9E9E;
}

.merge-preview {
  margin-top: 12px;
  padding: 12px;
  background: #E8F4E8;
  border-radius: 8px;
  font-size: 13px;
  color: #4A7C4A;
}
</style>