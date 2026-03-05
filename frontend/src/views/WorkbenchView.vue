<template>
  <div class="workbench-page">
    <!-- 顶部工具栏 -->
    <header class="workbench-header">
      <div class="header-left">
        <el-button text :icon="Back" @click="goBack">返回项目列表</el-button>
        <span class="project-title">{{ projectStore.currentProject?.title || '加载中...' }}</span>
      </div>
      <div class="header-right">
        <span class="total-words">
          总字数: {{ projectStore.currentProject?.current_word_count?.toLocaleString() || 0 }}
        </span>
      </div>
    </header>

    <!-- 三栏工作台主体 -->
    <div class="workbench-main">
      <!-- 左栏: 章节导航 -->
      <aside class="sidebar-left">
        <ChapterList :project-id="projectId" />
      </aside>

      <!-- 中栏: Tiptap 编辑器 -->
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

      <!-- 右栏: AI 助手面板 -->
      <aside class="sidebar-right">
        <AiPanel />
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Back } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useChapterStore } from '@/stores/chapter'
import ChapterList from '@/components/ChapterList.vue'
import TiptapEditor from '@/components/TiptapEditor.vue'
import AiPanel from '@/components/AiPanel.vue'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const chapterStore = useChapterStore()

// 项目 ID（从路由参数获取）
const projectId = computed(() => Number(route.params.id))

// 当前章节内容（双向绑定）
const currentContent = ref('')

// 触发创建章节（通过 event bus 或直接调用子组件方法）
function triggerCreateChapter() {
  // 通过设置一个临时状态触发 ChapterList 显示创建对话框
  // 这里简化处理：直接调用 store 创建
  chapterStore.createNewChapter(projectId.value, { title: '第一章' })
}

// 返回项目列表
function goBack() {
  router.push('/projects')
}

// 内容变化处理（防抖后触发自动保存）
async function handleContentChange(content: string) {
  if (!chapterStore.currentChapter) return

  // 更新章节内容
  await chapterStore.updateCurrentChapter(
    projectId.value,
    chapterStore.currentChapter.id,
    { content }
  )

  // 同步更新项目的总字数
  const totalWords = chapterStore.chapters.reduce((sum, ch) => sum + (ch.word_count || 0), 0)
  if (projectStore.currentProject && totalWords !== projectStore.currentProject.current_word_count) {
    await projectStore.updateCurrentProject(projectId.value, {
      current_word_count: totalWords,
    })
  }
}

// 监听当前章节变化，更新编辑器内容
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

// 页面加载时获取项目和章节数据
onMounted(async () => {
  await Promise.all([
    projectStore.fetchProject(projectId.value),
    chapterStore.fetchChapters(projectId.value),
  ])

  // 如果有章节，默认选中第一个
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

/* 顶部工具栏 */
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

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.project-title {
  font-size: 16px;
  font-weight: 600;
  color: #e2b714;
  font-family: 'Noto Serif SC', serif;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.total-words {
  font-size: 13px;
  color: #909399;
}

/* 三栏工作台 */
.workbench-main {
  flex: 1;
  display: flex;
  overflow: hidden;
}

/* 左侧边栏 - 章节导航 */
.sidebar-left {
  width: 240px;
  flex-shrink: 0;
  border-right: 1px solid #2d3561;
  overflow: hidden;
}

/* 中间编辑器区域 */
.editor-column {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.no-chapter-selected {
  flex: 1;
  display: flex;
  justify-content: center;
  align-items: center;
  background-color: #f8f6f0;
}

/* 右侧边栏 - AI 助手 */
.sidebar-right {
  width: 300px;
  flex-shrink: 0;
  border-left: 1px solid #2d3561;
  overflow: hidden;
}
</style>