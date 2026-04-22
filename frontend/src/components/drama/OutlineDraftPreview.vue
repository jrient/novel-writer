<template>
  <div class="outline-draft-preview">
    <div v-if="!sections.length" class="empty-state">
      <el-empty description="暂无大纲数据" :image-size="60" />
    </div>

    <div v-else class="episode-list">
      <div
        v-for="(ep, index) in sections"
        :key="index"
        class="episode-item"
        :class="{ 'episode-item--expanded': isExpanded(index) }"
      >
        <!-- 集标题行 -->
        <div class="episode-header">
          <div class="episode-meta">
            <span class="episode-index">第 {{ index + 1 }} 集</span>
            <span class="episode-title">{{ ep.title }}</span>
          </div>
          <div class="episode-actions">
            <el-tag v-if="isExpanded(index)" type="success" size="small">已生成</el-tag>
            <el-button
              v-if="!props.disableIndividual && !isExpanded(index)"
              size="small"
              :loading="expandingIndex === index"
              @click="handleExpand(index)"
            >
              生成内容
            </el-button>
            <el-button
              v-if="isExpanded(index) && !props.disableIndividual"
              size="small"
              type="warning"
              plain
              :loading="expandingIndex === index"
              @click="handleRegenerate(index)"
            >
              重新生成
            </el-button>
          </div>
        </div>

        <!-- 集概要 -->
        <p class="episode-summary">{{ ep.content }}</p>

        <!-- 已生成时显示完整内容预览 -->
        <div v-if="isExpanded(index)" class="episode-content-preview">
          <el-divider content-position="left">
            <el-tag size="small">完整内容</el-tag>
          </el-divider>
          <div class="full-content">{{ ep.content }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { streamExpandEpisode } from '@/api/drama'

interface EpisodeSection {
  node_type: string
  title: string
  content: string
  sort_order: number
  generated?: boolean
  children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}

const props = defineProps<{
  projectId: number
  sections: EpisodeSection[]
  disableIndividual?: boolean
}>()

const emit = defineEmits<{
  (e: 'episode-expanded', index: number): void
  (e: 'expanding-change', isExpanding: boolean): void
}>()

const expandingIndex = ref<number | null>(null)

function isExpanded(index: number): boolean {
  return props.sections[index]?.generated === true
}

function handleExpand(index: number) {
  if (expandingIndex.value !== null) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }
  expandingIndex.value = index
  emit('expanding-change', true)

  streamExpandEpisode(
    props.projectId,
    index,
    () => { /* chunk 忽略 */ },
    () => {
      expandingIndex.value = null
      emit('expanding-change', false)
      emit('episode-expanded', index)
    },
    (error) => {
      expandingIndex.value = null
      emit('expanding-change', false)
      ElMessage.error(`展开失败：${error}`)
    },
  )
}

function handleRegenerate(index: number) {
  if (expandingIndex.value !== null) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }
  expandingIndex.value = index
  emit('expanding-change', true)

  streamExpandEpisode(
    props.projectId,
    index,
    () => { /* chunk 忽略 */ },
    () => {
      expandingIndex.value = null
      emit('expanding-change', false)
      emit('episode-expanded', index)
      ElMessage.success('第 ' + (index + 1) + ' 集已重新生成')
    },
    (error) => {
      expandingIndex.value = null
      emit('expanding-change', false)
      ElMessage.error(`重新生成失败：${error}`)
    },
  )
}
</script>

<style scoped>
.outline-draft-preview {
  padding: 8px 0;
}

.episode-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.episode-item {
  border: 1px solid #ECEAE6;
  border-radius: 8px;
  padding: 12px 16px;
  background: #FAFAF9;
  transition: border-color 0.2s;
}

.episode-item--expanded {
  border-color: #67c23a;
  background: #f0f9eb;
}

.episode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.episode-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.episode-index {
  font-size: 12px;
  color: #9E9E9E;
  white-space: nowrap;
  flex-shrink: 0;
}

.episode-title {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.episode-actions {
  flex-shrink: 0;
}

.episode-summary {
  font-size: 13px;
  color: #6B7B8D;
  margin: 6px 0 0;
  line-height: 1.5;
}

.episode-content-preview {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #E8F5E9;
}

.full-content {
  font-size: 14px;
  color: #2C2C2C;
  line-height: 1.8;
  white-space: pre-wrap;
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
  background: #FAFAF9;
  border-radius: 4px;
}
</style>
