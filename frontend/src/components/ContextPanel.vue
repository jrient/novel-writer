<template>
  <div class="context-panel">
    <!-- 面板切换标签 -->
    <div class="panel-tabs">
      <el-radio-group v-model="activePanel" size="small">
        <el-radio-button label="ai">AI助手</el-radio-button>
        <el-radio-button label="characters">角色</el-radio-button>
        <el-radio-button label="worldbuilding">设定</el-radio-button>
        <el-radio-button label="events">事件</el-radio-button>
      </el-radio-group>
    </div>

    <!-- 面板内容 -->
    <div class="panel-content">
      <AiPanel
        v-if="activePanel === 'ai'"
        :current-chapter-title="currentChapterTitle"
        :current-content="currentContent"
        :project-id="projectId"
        :chapter-id="chapterId"
        @insert-text="$emit('insert-text', $event)"
        @replace-text="$emit('replace-text', $event)"
        @chapters-updated="$emit('chapters-updated')"
      />
      <CharacterPanel
        v-else-if="activePanel === 'characters'"
        :project-id="projectId"
      />
      <WorldbuildingPanel
        v-else-if="activePanel === 'worldbuilding'"
        :project-id="projectId"
      />
      <EventPanel
        v-else-if="activePanel === 'events'"
        :project-id="projectId"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AiPanel from './AiPanel.vue'
import CharacterPanel from './CharacterPanel.vue'
import WorldbuildingPanel from './WorldbuildingPanel.vue'
import EventPanel from './EventPanel.vue'

const props = defineProps<{
  projectId: number
  chapterId?: number
  currentChapterTitle?: string
  currentContent?: string
  defaultPanel?: string
}>()

defineEmits<{
  (e: 'insert-text', text: string): void
  (e: 'replace-text', text: string): void
  (e: 'chapters-updated'): void
}>()

const activePanel = ref(props.defaultPanel || 'ai')

// 当切换章节时，可以自动切换到 AI 面板
watch(() => props.chapterId, () => {
  // 可选：章节切换时自动切换到 AI 面板
  // activePanel.value = 'ai'
})
</script>

<style scoped>
.context-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: white;
}

.panel-tabs {
  padding: 8px;
  border-bottom: 1px solid #E0DFDC;
  background: #FAFAF8;
  flex-shrink: 0;
}

.panel-tabs :deep(.el-radio-group) {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.panel-tabs :deep(.el-radio-button__inner) {
  padding: 4px 8px;
  font-size: 12px;
  border-radius: 4px !important;
}

.panel-tabs :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: #6B7B8D;
  border-color: #6B7B8D;
}

.panel-content {
  flex: 1;
  overflow: hidden;
}
</style>