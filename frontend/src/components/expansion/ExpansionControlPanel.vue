<template>
  <div class="control-panel">
    <div class="panel-section">
      <h4 class="section-title">扩写设置</h4>

      <el-form label-position="top" size="small">
        <el-form-item label="扩写深度">
          <el-radio-group v-model="localConfig.expansion_level">
            <el-radio-button value="light">轻度</el-radio-button>
            <el-radio-button value="medium">中度</el-radio-button>
            <el-radio-button value="deep">深度</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="目标字数">
          <el-input-number
            v-model="localConfig.target_word_count"
            :min="0"
            :max="200000"
            :step="1000"
            style="width: 100%"
          />
        </el-form-item>

        <el-form-item label="风格指导">
          <el-input
            v-model="localConfig.style_instructions"
            type="textarea"
            :rows="3"
            placeholder="输入风格指导..."
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- Segment-specific settings -->
    <div v-if="currentSegment" class="panel-section">
      <h4 class="section-title">当前段落</h4>

      <div class="segment-info">
        <div class="info-row">
          <span class="info-label">段落：</span>
          <span class="info-value">{{ currentSegment.title || `第${currentSegment.sort_order + 1}段` }}</span>
        </div>
        <div class="info-row">
          <span class="info-label">原文：</span>
          <span class="info-value">{{ currentSegment.original_word_count }} 字</span>
        </div>
        <div v-if="currentSegment.expanded_word_count" class="info-row">
          <span class="info-label">扩写：</span>
          <span class="info-value success">{{ currentSegment.expanded_word_count }} 字</span>
        </div>
      </div>

      <el-form label-position="top" size="small">
        <el-form-item label="自定义指令">
          <el-input
            v-model="segmentInstructions"
            type="textarea"
            :rows="2"
            placeholder="针对此段的自定义指令..."
          />
        </el-form-item>
      </el-form>
    </div>

    <!-- Action buttons -->
    <div class="panel-section actions-section">
      <el-button
        v-if="currentSegment && currentSegment.status !== 'completed'"
        type="primary"
        :loading="isExpandingCurrent"
        :disabled="isPaused"
        @click="expandCurrentSegment"
        style="width: 100%"
      >
        <el-icon><VideoPlay /></el-icon>
        扩写此段
      </el-button>

      <el-button
        v-if="currentSegment"
        size="small"
        @click="$emit('split')"
        style="width: 100%"
      >
        <el-icon><Scissor /></el-icon>
        拆分此段
      </el-button>

      <el-button
        v-if="currentSegment?.status === 'error'"
        type="warning"
        :loading="isRetrying"
        @click="retryCurrentSegment"
        style="width: 100%"
      >
        <el-icon><RefreshRight /></el-icon>
        重试此段
      </el-button>

      <el-divider />

      <el-button
        v-if="!isExpanding"
        type="success"
        :disabled="!hasPendingSegments"
        @click="expandAll"
        style="width: 100%"
      >
        <el-icon><VideoPlay /></el-icon>
        全部扩写
      </el-button>

      <template v-else>
        <el-button
          v-if="!isPaused"
          type="warning"
          @click="pauseExpansion"
          style="width: 100%"
        >
          <el-icon><VideoPause /></el-icon>
          暂停扩写
        </el-button>

        <el-button
          v-else
          type="success"
          @click="resumeExpansion"
          style="width: 100%"
        >
          <el-icon><VideoPlay /></el-icon>
          继续扩写
        </el-button>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { VideoPlay, VideoPause, RefreshRight, Scissor } from '@element-plus/icons-vue'
import type { ExpansionSegment } from '@/api/expansion'

const props = defineProps<{
  projectStatus: string
  currentSegment: ExpansionSegment | null
  isExpanding: boolean
  isPaused: boolean
  hasPendingSegments: boolean
}>()

const emit = defineEmits<{
  'update:config': [config: { expansion_level: string; target_word_count: number | null; style_instructions: string }]
  'expand-segment': [segmentId: number, instructions: string]
  'expand-all': []
  'pause': []
  'resume': []
  'retry': [segmentId: number]
  'split': []
}>()

const localConfig = ref({
  expansion_level: 'medium' as 'light' | 'medium' | 'deep',
  target_word_count: null as number | null,
  style_instructions: '',
})

const segmentInstructions = ref('')
const isExpandingCurrent = computed(() => props.isExpanding && props.currentSegment?.status === 'expanding')
const isRetrying = ref(false)

// Sync with parent config
watch(() => localConfig.value, (val) => {
  emit('update:config', val)
}, { deep: true })

function expandCurrentSegment() {
  if (props.currentSegment) {
    emit('expand-segment', props.currentSegment.id, segmentInstructions.value)
  }
}

function expandAll() {
  emit('expand-all')
}

function pauseExpansion() {
  emit('pause')
}

function resumeExpansion() {
  emit('resume')
}

function retryCurrentSegment() {
  if (props.currentSegment) {
    emit('retry', props.currentSegment.id)
  }
}
</script>

<style scoped>
.control-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: #FAFAFA;
  overflow-y: auto;
}

.panel-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0 0 12px 0;
  padding-bottom: 8px;
  border-bottom: 1px solid #E0DFDC;
}

.segment-info {
  background: white;
  padding: 12px;
  border-radius: 8px;
  margin-bottom: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  line-height: 1.8;
}

.info-label {
  color: #9E9E9E;
}

.info-value {
  color: #5C5C5C;
  font-weight: 500;
}

.info-value.success {
  color: #52C41A;
}

.actions-section {
  margin-top: auto;
  padding-top: 16px;
}

:deep(.el-form-item) {
  margin-bottom: 12px;
}

:deep(.el-form-item__label) {
  font-size: 12px;
  color: #7A7A7A;
}
</style>