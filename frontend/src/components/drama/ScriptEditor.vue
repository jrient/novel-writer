<template>
  <div class="script-editor">
    <!-- No node selected -->
    <div v-if="!node" class="no-node">
      <el-empty description="请在左侧大纲中选择一个节点开始编辑" :image-size="80">
        <template #image>
          <el-icon class="empty-icon"><Document /></el-icon>
        </template>
      </el-empty>
    </div>

    <template v-else>
      <!-- Editor header -->
      <div class="editor-header">
        <div class="node-type-badge">
          <NodeTypeIcon :node-type="node.node_type" />
          <span class="node-type-label">{{ nodeTypeLabel }}</span>
        </div>
        <el-input
          v-model="localTitle"
          class="title-input"
          placeholder="节点标题..."
          @change="handleTitleChange"
        />
        <div class="header-actions">
          <el-button
            v-if="node.node_type === 'episode'"
            size="small"
            text
            @click="showVersions = true"
          >
            <el-icon><Clock /></el-icon>
            历史版本
          </el-button>
          <el-tag v-if="node.is_completed" type="success" size="small" effect="plain">已完成</el-tag>
          <span v-if="saveStatus" class="save-status">{{ saveStatus }}</span>
        </div>
      </div>

      <!-- Speaker input for dialogue nodes -->
      <div v-if="node.node_type === 'dialogue'" class="speaker-row">
        <span class="speaker-label">说话人：</span>
        <el-input
          v-model="localSpeaker"
          placeholder="角色名称"
          size="small"
          style="width: 180px"
          @change="handleSpeakerChange"
        />
      </div>

      <!-- Visual description for scene nodes -->
      <div v-if="showVisualDesc" class="visual-desc-row">
        <span class="visual-desc-label">视觉描述：</span>
        <el-input
          v-model="localVisualDesc"
          type="textarea"
          :autosize="{ minRows: 1, maxRows: 3 }"
          placeholder="画面描述..."
          size="small"
          @input="handleVisualDescInput"
        />
      </div>

      <!-- Main content editor -->
      <div class="content-area">
        <el-input
          v-model="localContent"
          type="textarea"
          :autosize="{ minRows: 10 }"
          :placeholder="contentPlaceholder"
          class="content-textarea"
          @input="handleContentInput"
        />
      </div>

      <!-- Version history dialog for episode nodes -->
      <VersionHistoryDialog
        v-if="node?.node_type === 'episode'"
        v-model="showVersions"
        :project-id="projectId"
        :node-id="node.id"
        @restored="emit('version-restored')"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Document, Clock } from '@element-plus/icons-vue'
import type { ScriptNode } from '@/api/drama'
import NodeTypeIcon from './NodeTypeIcon.vue'
import VersionHistoryDialog from './VersionHistoryDialog.vue'

const props = defineProps<{
  node: ScriptNode | null
  scriptType: 'explanatory' | 'dynamic'
  projectId: number
}>()

const emit = defineEmits<{
  (e: 'save', data: { title?: string; content?: string; speaker?: string; visual_desc?: string }): void
  (e: 'version-restored'): void
}>()

const localTitle = ref('')
const localContent = ref('')
const localSpeaker = ref('')
const localVisualDesc = ref('')
const saveStatus = ref('')
const showVersions = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null

const nodeTypeLabels: Record<string, string> = {
  episode: '集',
  scene: '场景',
  dialogue: '对白',
  action: '动作',
  effect: '特效',
  inner_voice: '内心独白',
  section: '章节',
  narration: '旁白',
  intro: '介绍',
}

const nodeTypeLabel = computed(() => nodeTypeLabels[props.node?.node_type || ''] || props.node?.node_type || '')

const showVisualDesc = computed(() =>
  props.node?.node_type === 'scene' || props.node?.node_type === 'action' || props.node?.node_type === 'effect'
)

const contentPlaceholder = computed(() => {
  if (!props.node) return ''
  const typeMap: Record<string, string> = {
    dialogue: '输入对白内容...',
    action: '描述动作...',
    narration: '输入旁白文字...',
    inner_voice: '描述角色的内心独白...',
    scene: '描述场景内容...',
    effect: '描述特效或音效...',
    episode: '输入本集内容...',
    section: '输入章节内容...',
    intro: '输入介绍内容...',
  }
  return typeMap[props.node.node_type] || '输入内容...'
})

watch(
  () => props.node,
  (node) => {
    if (node) {
      localTitle.value = node.title || ''
      localContent.value = node.content || ''
      localSpeaker.value = node.speaker || ''
      localVisualDesc.value = node.visual_desc || ''
      saveStatus.value = ''
    }
  },
  { immediate: true },
)

function scheduleSave(data: Parameters<typeof emit>[1]) {
  if (saveTimer) clearTimeout(saveTimer)
  saveStatus.value = '编辑中...'
  saveTimer = setTimeout(() => {
    emit('save', data)
    saveStatus.value = '已保存'
    setTimeout(() => { saveStatus.value = '' }, 1500)
  }, 500)
}

function handleTitleChange() {
  scheduleSave({ title: localTitle.value })
}

function handleContentInput() {
  scheduleSave({ content: localContent.value })
}

function handleSpeakerChange() {
  scheduleSave({ speaker: localSpeaker.value })
}

function handleVisualDescInput() {
  scheduleSave({ visual_desc: localVisualDesc.value })
}
</script>

<style scoped>
.script-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #F7F6F3;
  overflow: hidden;
}

.no-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-icon {
  font-size: 64px;
  color: #C8C6C2;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
  flex-shrink: 0;
}

.node-type-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(107, 123, 141, 0.08);
  padding: 4px 10px;
  border-radius: 20px;
  flex-shrink: 0;
}

.node-type-label {
  font-size: 12px;
  color: #6B7B8D;
  font-weight: 500;
}

.title-input {
  flex: 1;
}

:deep(.title-input .el-input__inner) {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
  border: none;
  background: transparent;
  padding-left: 0;
}

:deep(.title-input .el-input__wrapper) {
  box-shadow: none !important;
  background: transparent;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.save-status {
  font-size: 12px;
  color: #9E9E9E;
}

.speaker-row,
.visual-desc-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 20px;
  background: white;
  border-bottom: 1px solid #ECEAE6;
  flex-shrink: 0;
}

.speaker-label,
.visual-desc-label {
  font-size: 13px;
  color: #7A7A7A;
  padding-top: 4px;
  flex-shrink: 0;
  width: 70px;
}

.content-area {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.content-textarea {
  width: 100%;
}

:deep(.content-textarea .el-textarea__inner) {
  font-size: 14px;
  line-height: 1.8;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 10px;
  padding: 16px;
  resize: none;
  box-shadow: 0 1px 4px rgba(44, 44, 44, 0.04);
  transition: border-color 0.2s;
}

:deep(.content-textarea .el-textarea__inner:focus) {
  border-color: #6B7B8D;
  box-shadow: 0 0 0 3px rgba(107, 123, 141, 0.08);
}
</style>
