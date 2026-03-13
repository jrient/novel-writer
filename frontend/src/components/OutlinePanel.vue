<template>
  <div class="outline-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">故事大纲</span>
      <div class="header-actions">
        <span class="word-count" v-if="charCount > 0">{{ charCount }} 字</span>
      </div>
    </div>

    <!-- 大纲编辑器 -->
    <div class="outline-editor">
      <TiptapEditor
        v-model="outlineContent"
        :saving="saving"
        @change="handleContentChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import TiptapEditor from './TiptapEditor.vue'
import { useProjectStore } from '@/stores/project'

const props = defineProps<{
  projectId: number
}>()

const projectStore = useProjectStore()

const outlineContent = ref('')
const saving = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// 计算字数
const charCount = computed(() => {
  return outlineContent.value.length
})

// 监听当前项目变化，加载大纲内容
watch(
  () => projectStore.currentProject,
  (project) => {
    if (project && project.id === props.projectId) {
      outlineContent.value = project.outline || ''
    }
  },
  { immediate: true }
)

// 处理内容变化，自动保存
async function handleContentChange(content: string) {
  if (debounceTimer) clearTimeout(debounceTimer)

  debounceTimer = setTimeout(async () => {
    saving.value = true
    try {
      await projectStore.updateCurrentProject(props.projectId, {
        outline: content
      })
    } finally {
      saving.value = false
    }
  }, 500)
}

// 组件挂载时加载项目数据
onMounted(async () => {
  if (!projectStore.currentProject || projectStore.currentProject.id !== props.projectId) {
    await projectStore.fetchProject(props.projectId)
  }
})
</script>

<style scoped>
.outline-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #F7F6F3;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 32px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.word-count {
  font-size: 12px;
  color: #9E9E9E;
  font-weight: 500;
}

.outline-editor {
  flex: 1;
  overflow: hidden;
}
</style>