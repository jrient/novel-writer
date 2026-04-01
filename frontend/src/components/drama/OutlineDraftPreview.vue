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
            <el-tag v-if="isExpanded(index)" type="success" size="small">已展开</el-tag>
            <el-button
              v-else
              size="small"
              :loading="expandingIndex === index"
              @click="handleExpand(index)"
            >
              展开场景
            </el-button>
          </div>
        </div>

        <!-- 集概要 -->
        <p class="episode-summary">{{ ep.content }}</p>

        <!-- 已展开的场景列表 -->
        <div v-if="isExpanded(index)" class="scene-list">
          <div
            v-for="(scene, si) in ep.children"
            :key="si"
            class="scene-item"
          >
            <span class="scene-index">场景 {{ si + 1 }}</span>
            <span class="scene-title">{{ scene.title }}</span>
          </div>
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
  children: Array<{ node_type: string; title: string; content: string; sort_order: number }>
}

const props = defineProps<{
  projectId: number
  sections: EpisodeSection[]
}>()

const emit = defineEmits<{
  (e: 'episode-expanded', index: number): void
}>()

const expandingIndex = ref<number | null>(null)

function isExpanded(index: number): boolean {
  return (props.sections[index]?.children?.length ?? 0) > 0
}

function handleExpand(index: number) {
  if (expandingIndex.value !== null) {
    ElMessage.warning('请等待当前集展开完成')
    return
  }
  expandingIndex.value = index

  streamExpandEpisode(
    props.projectId,
    index,
    () => { /* chunk 忽略，完成后刷新 */ },
    () => {
      expandingIndex.value = null
      emit('episode-expanded', index)
    },
    (error) => {
      expandingIndex.value = null
      ElMessage.error(`展开失败：${error}`)
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

.scene-list {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #E8F5E9;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.scene-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.scene-index {
  color: #9E9E9E;
  flex-shrink: 0;
}

.scene-title {
  color: #4CAF50;
}
</style>
