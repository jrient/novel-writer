<template>
  <div class="workbench-page">
    <!-- 顶部工具栏 -->
    <header class="workbench-header">
      <div class="header-left">
        <el-button text :icon="Back" @click="goBack">返回</el-button>
        <span class="project-title">{{ projectStore.currentProject?.title || '加载中...' }}</span>
        <el-tag v-if="projectStore.currentProject?.genre" size="small" effect="plain" class="genre-tag">
          {{ projectStore.currentProject.genre }}
        </el-tag>
      </div>
      <div class="header-center">
        <el-radio-group v-model="activeTab" size="small">
          <el-radio-button label="editor">写作</el-radio-button>
          <el-radio-button label="characters">角色</el-radio-button>
          <el-radio-button label="worldbuilding">设定</el-radio-button>
          <el-radio-button label="outline">大纲</el-radio-button>
        </el-radio-group>
      </div>
      <div class="header-right">
        <span class="total-words">
          {{ projectStore.currentProject?.current_word_count?.toLocaleString() || 0 }} 字
        </span>
        <el-progress
          v-if="wordProgress > 0"
          type="circle"
          :percentage="wordProgress"
          :width="28"
          :stroke-width="3"
          color="#e2b714"
          :show-text="false"
          class="progress-circle"
        />
        <el-dropdown trigger="click" @command="handleExport">
          <el-button text size="small" class="export-btn">
            <el-icon><Download /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="txt">导出 TXT</el-dropdown-item>
              <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
              <el-dropdown-item command="markdown-full">导出 Markdown（含角色）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <!-- 主内容区 -->
    <div class="workbench-main">
      <!-- 写作模式：三栏布局 -->
      <template v-if="activeTab === 'editor'">
        <aside class="sidebar-left">
          <ChapterList :project-id="projectId" />
        </aside>
        <main class="editor-column">
          <div v-if="!chapterStore.currentChapter" class="no-chapter-selected">
            <el-empty description="请选择或创建一个章节开始创作">
              <el-button type="primary" @click="triggerCreateChapter">创建第一章</el-button>
            </el-empty>
          </div>
          <TiptapEditor
            v-else
            v-model="currentContent"
            :saving="chapterStore.saving"
            @change="handleContentChange"
          />
        </main>
        <aside class="sidebar-right">
          <AiPanel
            :current-chapter-title="chapterStore.currentChapter?.title"
            :current-content="currentContent"
            :project-id="projectId"
            :chapter-id="chapterStore.currentChapter?.id"
            @insert-text="handleInsertText"
          />
        </aside>
      </template>

      <!-- Story Bible 面板 -->
      <template v-else>
        <div class="story-bible-panel">
          <CharacterPanel v-if="activeTab === 'characters'" :project-id="projectId" />
          <WorldbuildingPanel v-else-if="activeTab === 'worldbuilding'" :project-id="projectId" />
          <OutlinePanel v-else-if="activeTab === 'outline'" :project-id="projectId" />
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { useChapterStore } from '@/stores/chapter'
import ChapterList from '@/components/ChapterList.vue'
import TiptapEditor from '@/components/TiptapEditor.vue'
import AiPanel from '@/components/AiPanel.vue'
import CharacterPanel from '@/components/CharacterPanel.vue'
import WorldbuildingPanel from '@/components/WorldbuildingPanel.vue'
import OutlinePanel from '@/components/OutlinePanel.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const chapterStore = useChapterStore()

const projectId = computed(() => Number(route.params.id))
const currentContent = ref('')
const activeTab = ref('editor')

const wordProgress = computed(() => {
  const p = projectStore.currentProject
  if (!p || !p.target_word_count) return 0
  return Math.min(Math.round((p.current_word_count / p.target_word_count) * 100), 100)
})

function triggerCreateChapter() {
  chapterStore.createNewChapter(projectId.value, { title: '第一章' })
}

function goBack() {
  router.push('/projects')
}

function handleInsertText(text: string) {
  if (!chapterStore.currentChapter) return
  currentContent.value = currentContent.value + '\n\n' + text
  handleContentChange(currentContent.value)
}

async function handleExport(format: string) {
  try {
    let url = `/api/v1/projects/${projectId.value}/export/`
    if (format === 'markdown-full') {
      url += 'markdown?include_characters=true'
    } else {
      url += format
    }
    const resp = await fetch(url)
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    const ext = format.startsWith('markdown') ? 'md' : 'txt'
    const title = projectStore.currentProject?.title || 'export'
    a.download = `${title}.${ext}`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function handleContentChange(content: string) {
  if (!chapterStore.currentChapter) return

  await chapterStore.updateCurrentChapter(
    projectId.value,
    chapterStore.currentChapter.id,
    { content }
  )

  const totalWords = chapterStore.chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0)
  if (projectStore.currentProject && totalWords !== projectStore.currentProject.current_word_count) {
    await projectStore.updateCurrentProject(projectId.value, {
      current_word_count: totalWords,
    })
  }
}

watch(
  () => chapterStore.currentChapter,
  (chapter) => {
    if (chapter) {
      currentContent.value = chapter.content || ''
    } else {
      currentContent.value = ''
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await Promise.all([
    projectStore.fetchProject(projectId.value),
    chapterStore.fetchChapters(projectId.value),
  ])

  if (chapterStore.chapters.length > 0 && !chapterStore.currentChapter) {
    chapterStore.setCurrentChapter(chapterStore.chapters[0])
  }
})
</script>

<style scoped>
.workbench-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #1a1a2e;
}

.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 48px;
  padding: 0 16px;
  background-color: #16213e;
  border-bottom: 1px solid #2d3561;
  flex-shrink: 0;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-center {
  display: flex;
  align-items: center;
}

.project-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2b714;
  font-family: 'Noto Serif SC', serif;
}

.genre-tag {
  color: #909399 !important;
  border-color: #2d3561 !important;
  background-color: transparent !important;
}

.total-words {
  font-size: 13px;
  color: #909399;
  font-weight: 500;
}

.progress-circle {
  margin-left: -4px;
}

.export-btn {
  color: #909399 !important;
}

.export-btn:hover {
  color: #e2b714 !important;
}

.workbench-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.sidebar-left {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #2d3561;
  overflow: hidden;
}

.editor-column {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.sidebar-right {
  width: 300px;
  flex-shrink: 0;
  border-left: 1px solid #2d3561;
  overflow: hidden;
}

.no-chapter-selected {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f8f6f0;
}

.story-bible-panel {
  flex: 1;
  overflow: hidden;
}

:deep(.el-radio-button__inner) {
  background-color: transparent;
  border-color: #2d3561;
  color: #909399;
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background-color: #e2b714;
  border-color: #e2b714;
  color: #1a1a2e;
}
</style>
