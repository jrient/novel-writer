<template>
  <div class="compare-panel">
    <div class="compare-content">
      <!-- Original content -->
      <div class="content-panel original-panel">
        <div class="panel-header">
          <span class="panel-title">原文</span>
          <span class="word-count">{{ originalWordCount.toLocaleString() }} 字</span>
        </div>
        <div class="panel-body">
          <div v-if="!originalContent" class="empty-state">
            请选择一个段落
          </div>
          <div v-else class="content-text">{{ originalContent }}</div>
        </div>
      </div>

      <!-- Expanded content -->
      <div class="content-panel expanded-panel">
        <div class="panel-header">
          <span class="panel-title">扩写内容</span>
          <span v-if="expandedWordCount" class="word-count">{{ expandedWordCount.toLocaleString() }} 字</span>
        </div>
        <div class="panel-body">
          <div v-if="isExpanding && !expandedContent" class="expanding-state">
            <el-icon class="is-loading"><Loading /></el-icon>
            <span>AI 正在扩写...</span>
          </div>
          <div v-else-if="!expandedContent" class="empty-state">
            尚未扩写
          </div>
          <div v-else class="content-text">
            {{ expandedContent }}
            <span v-if="isExpanding" class="cursor-blink">|</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Comparison bar -->
    <div v-if="expandedWordCount" class="comparison-bar">
      <div class="comparison-label">
        字数变化：{{ originalWordCount.toLocaleString() }} → {{ expandedWordCount.toLocaleString() }}
      </div>
      <div class="comparison-stats">
        <span :class="expansionRatio >= 0 ? 'positive' : 'negative'">
          {{ expansionRatio >= 0 ? '+' : '' }}{{ expansionRatio.toFixed(0) }}%
        </span>
      </div>
      <el-progress
        :percentage="Math.min(100, (expandedWordCount / originalWordCount) * 100)"
        :stroke-width="6"
        :show-text="false"
        :color="progressColor"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Loading } from '@element-plus/icons-vue'

const props = defineProps<{
  originalContent: string
  expandedContent: string
  originalWordCount: number
  expandedWordCount: number | null
  isExpanding: boolean
}>()

const expansionRatio = computed(() => {
  if (!props.expandedWordCount || !props.originalWordCount) return 0
  return ((props.expandedWordCount - props.originalWordCount) / props.originalWordCount) * 100
})

const progressColor = computed(() => {
  const ratio = expansionRatio.value
  if (ratio < 0) return '#F56C6C'
  if (ratio < 50) return '#E6A23C'
  return '#52C41A'
})
</script>

<style scoped>
.compare-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.compare-content {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}

.content-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  background: white;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: #F5F5F5;
  border-bottom: 1px solid #E0DFDC;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #5C5C5C;
}

.word-count {
  font-size: 12px;
  color: #9E9E9E;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}

.content-text {
  font-size: 14px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-word;
}

.empty-state,
.expanding-state {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #9E9E9E;
  font-size: 14px;
}

.expanding-state {
  gap: 8px;
}

.cursor-blink {
  animation: blink 1s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.comparison-bar {
  padding: 12px 16px;
  background: #F5F5F5;
  border-radius: 8px;
  margin-top: 12px;
}

.comparison-label {
  font-size: 12px;
  color: #7A7A7A;
  margin-bottom: 8px;
}

.comparison-stats {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 6px;
}

.comparison-stats .positive {
  color: #52C41A;
  font-weight: 600;
}

.comparison-stats .negative {
  color: #F56C6C;
  font-weight: 600;
}
</style>