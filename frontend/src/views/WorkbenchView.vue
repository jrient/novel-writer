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
          <el-radio-button label="events">事件</el-radio-button>
          <el-radio-button label="knowledge">知识库</el-radio-button>
        </el-radio-group>
      </div>
      <div class="header-right">
        <el-button text size="small" class="miaoji-btn" @click="showMiaoji = true">
          <el-icon><EditPen /></el-icon>
          妙记
        </el-button>
        <span class="total-words">
          {{ projectStore.currentProject?.current_word_count?.toLocaleString() || 0 }} 字
        </span>
        <el-progress
          v-if="wordProgress > 0"
          type="circle"
          :percentage="wordProgress"
          :width="28"
          :stroke-width="3"
          color="#6B7B8D"
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
          <template v-else>
            <div class="editor-header">
              <span class="chapter-title-display">{{ chapterStore.currentChapter.title }}</span>
              <el-button
                size="small"
                @click="showVersionDrawer = true"
                class="version-btn"
              >
                <el-icon><Clock /></el-icon>
                历史版本
              </el-button>
            </div>
            <TiptapEditor
              v-model="currentContent"
              :saving="chapterStore.saving"
              :has-unsaved-changes="hasUnsavedChanges"
              @change="handleContentChange"
              @save="handleManualSave"
            />
          </template>
        </main>
        <aside class="sidebar-right">
          <AiPanel
            :current-chapter-title="chapterStore.currentChapter?.title"
            :current-content="currentContent"
            :project-id="projectId"
            :chapter-id="chapterStore.currentChapter?.id"
            @insert-text="handleInsertText"
            @replace-text="handleReplaceText"
            @chapters-updated="handleChaptersUpdated"
          />
        </aside>
      </template>

      <!-- Story Bible 面板 -->
      <template v-else>
        <div class="story-bible-panel">
          <CharacterPanel v-if="activeTab === 'characters'" :project-id="projectId" />
          <WorldbuildingPanel v-else-if="activeTab === 'worldbuilding'" :project-id="projectId" />
          <OutlinePanel v-else-if="activeTab === 'outline'" :project-id="projectId" />
          <EventPanel v-else-if="activeTab === 'events'" :project-id="projectId" />
          <KnowledgePanel v-else-if="activeTab === 'knowledge'" />
        </div>
      </template>
    </div>

    <!-- 版本历史抽屉（全局，不受 tab 切换影响） -->
    <ChapterVersionDrawer
      v-model="showVersionDrawer"
      :project-id="projectId"
      :chapter-id="chapterStore.currentChapter?.id || null"
      @restored="handleVersionRestored"
    />

    <!-- 妙记面板 -->
    <MiaojiPanel
      v-model="showMiaoji"
      :project-id="projectId"
      @parsed="handleMiaojiParsed"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back, Download, Clock, EditPen } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { useChapterStore } from '@/stores/chapter'
import ChapterList from '@/components/ChapterList.vue'
import TiptapEditor from '@/components/TiptapEditor.vue'
import AiPanel from '@/components/AiPanel.vue'
import CharacterPanel from '@/components/CharacterPanel.vue'
import WorldbuildingPanel from '@/components/WorldbuildingPanel.vue'
import OutlinePanel from '@/components/OutlinePanel.vue'
import KnowledgePanel from '@/components/KnowledgePanel.vue'
import EventPanel from '@/components/EventPanel.vue'
import ChapterVersionDrawer from '@/components/ChapterVersionDrawer.vue'
import MiaojiPanel from '@/components/MiaojiPanel.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const chapterStore = useChapterStore()

const projectId = computed(() => Number(route.params.id))
const currentContent = ref('')
const activeTab = ref('editor')
const showVersionDrawer = ref(false)
const showMiaoji = ref(false)
const hasUnsavedChanges = ref(false)

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

function handleReplaceText(text: string) {
  if (!chapterStore.currentChapter) return
  currentContent.value = text
  handleContentChange(currentContent.value)
}

async function handleChaptersUpdated() {
  // 刷新章节列表
  await chapterStore.fetchChapters(projectId.value)
}

async function handleVersionRestored() {
  // 版本恢复后刷新章节数据
  if (chapterStore.currentChapter) {
    await chapterStore.fetchChapters(projectId.value)
    // 重新选中当前章节以获取最新内容
    const updated = chapterStore.chapters.find(c => c.id === chapterStore.currentChapter?.id)
    if (updated) {
      chapterStore.setCurrentChapter(updated)
      currentContent.value = updated.content || ''
    }
  }
}

// 妙记解析完成后刷新数据
async function handleMiaojiParsed() {
  // 刷新所有可能被更新的数据
  await chapterStore.fetchChapters(projectId.value)
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

  hasUnsavedChanges.value = true
  await chapterStore.updateCurrentChapter(
    projectId.value,
    chapterStore.currentChapter.id,
    { content }
  )
  hasUnsavedChanges.value = false

  const totalWords = chapterStore.chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0)
  if (projectStore.currentProject && totalWords !== projectStore.currentProject.current_word_count) {
    await projectStore.updateCurrentProject(projectId.value, {
      current_word_count: totalWords,
    })
  }
}

// 手动保存（Ctrl+S 或点击保存按钮）
async function handleManualSave(content: string) {
  if (!chapterStore.currentChapter) return

  hasUnsavedChanges.value = true
  await chapterStore.updateCurrentChapter(
    projectId.value,
    chapterStore.currentChapter.id,
    { content }
  )
  hasUnsavedChanges.value = false
  ElMessage.success('保存成功')

  const totalWords = chapterStore.chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0)
  if (projectStore.currentProject && totalWords !== projectStore.currentProject.current_word_count) {
    await projectStore.updateCurrentProject(projectId.value, {
      current_word_count: totalWords,
    })
  }
}

watch(
  () => chapterStore.currentChapter,
  (chapter, oldChapter) => {
    if (chapter) {
      // 只有章节切换时才重置内容，避免保存后光标跳动
      const isChapterChanged = !oldChapter || chapter.id !== oldChapter.id
      if (isChapterChanged || !hasUnsavedChanges.value) {
        currentContent.value = chapter.content || ''
        hasUnsavedChanges.value = false
      }
    } else {
      currentContent.value = ''
      hasUnsavedChanges.value = false
    }
  },
  { immediate: true }
)

watch(() => chapterStore.saving, (saving) => {
  if (!saving) hasUnsavedChanges.value = false
})

function handleBeforeUnload(e: BeforeUnloadEvent) {
  if (hasUnsavedChanges.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onMounted(async () => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  await Promise.all([
    projectStore.fetchProject(projectId.value),
    chapterStore.fetchChapters(projectId.value),
  ])

  // 设置页面标题为项目名
  if (projectStore.currentProject?.title) {
    document.title = `${projectStore.currentProject.title} - AI小说创作平台`
  }

  if (chapterStore.chapters.length > 0 && !chapterStore.currentChapter) {
    chapterStore.setCurrentChapter(chapterStore.chapters[0])
  }
})

onUnmounted(() => {
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<style scoped>
.workbench-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #F7F6F3;
}

.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 56px;
  padding: 0 24px;
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(44, 44, 44, 0.03);
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-center {
  display: flex;
  align-items: center;
}

.project-title {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
}

.genre-tag {
  color: #7A7A7A !important;
  border-color: #E0DFDC !important;
  background-color: #F7F6F3 !important;
}

.total-words {
  font-size: 14px;
  color: #5C5C5C;
  font-weight: 500;
}

.progress-circle {
  margin-left: -4px;
}

.export-btn {
  color: #5C5C5C !important;
}

.export-btn:hover {
  color: #6B7B8D !important;
}

.workbench-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.sidebar-left {
  width: 260px;
  flex-shrink: 0;
  border-right: 1px solid #E0DFDC;
  overflow: hidden;
  background: white;
}

.editor-column {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #F7F6F3;
}

.editor-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 24px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
  flex-shrink: 0;
}

.chapter-title-display {
  font-size: 14px;
  font-weight: 500;
  color: #5C5C5C;
}

.version-btn {
  color: #6B7B8D;
  border-color: #E0DFDC;
}

.version-btn:hover {
  color: #5A6B7A;
  border-color: #6B7B8D;
  background-color: rgba(107, 123, 141, 0.05);
}

.miaoji-btn {
  color: #e6a23c;
  font-weight: 500;
}

.miaoji-btn:hover {
  color: #cf9236;
  background-color: rgba(230, 162, 60, 0.1);
}

.sidebar-right {
  width: 340px;
  flex-shrink: 0;
  border-left: 1px solid #E0DFDC;
  overflow: hidden;
  background: white;
}

.no-chapter-selected {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #F7F6F3;
}

.story-bible-panel {
  flex: 1;
  overflow: hidden;
  background: #F7F6F3;
}

:deep(.el-radio-button__inner) {
  background-color: transparent;
  border-color: #E0DFDC;
  color: #5C5C5C;
  border-radius: 8px;
  padding: 8px 16px;
  font-weight: 500;
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  border-color: transparent;
  color: white;
}

:deep(.el-button--text) {
  color: #5C5C5C;
}

:deep(.el-button--text:hover) {
  color: #6B7B8D;
}

/* 响应式适配 */
@media (max-width: 1024px) {
  .sidebar-right {
    width: 280px;
  }
}

@media (max-width: 768px) {
  .workbench-main {
    flex-direction: column;
  }

  .sidebar-left {
    width: 100%;
    height: 200px;
    border-right: none;
    border-bottom: 1px solid #E0DFDC;
  }

  .sidebar-right {
    width: 100%;
    height: 300px;
    border-left: none;
    border-top: 1px solid #E0DFDC;
  }

  .workbench-header {
    padding: 0 12px;
  }

  .header-right {
    gap: 8px;
  }

  .editor-column {
    min-height: 300px;
  }
}
</style>
