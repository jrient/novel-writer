<template>
  <div class="project-list-page">
    <!-- 顶部导航栏 -->
    <header class="page-header">
      <div class="header-content">
        <div class="logo-area">
          <span class="logo-icon">&#9997;</span>
          <h1 class="logo">AI小说创作平台</h1>
        </div>
        <el-button type="primary" :icon="Plus" @click="goToWizard" round>
          新建项目
        </el-button>
      </div>
    </header>

    <!-- 主体内容 -->
    <main class="page-main">
      <!-- 总览统计 -->
      <div class="stats-bar" v-if="projectStore.projects.length > 0">
        <div class="stat-item">
          <span class="stat-value">{{ projectStore.projects.length }}</span>
          <span class="stat-label">项目总数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ totalWords.toLocaleString() }}</span>
          <span class="stat-label">总字数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ writingCount }}</span>
          <span class="stat-label">创作中</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ completedCount }}</span>
          <span class="stat-label">已完成</span>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="projectStore.loading" class="loading-container">
        <el-skeleton :rows="3" animated />
      </div>

      <!-- 空状态 -->
      <div v-else-if="projectStore.projects.length === 0" class="empty-state">
        <div class="empty-icon">&#9997;</div>
        <h2 class="empty-title">开始你的创作之旅</h2>
        <p class="empty-desc">点击下方按钮创建第一个项目</p>
        <el-button type="primary" size="large" @click="goToWizard" round>创建第一个项目</el-button>
      </div>

      <!-- 项目网格 -->
      <div v-else class="projects-grid">
        <el-card
          v-for="project in projectStore.projects"
          :key="project.id"
          class="project-card"
          shadow="hover"
          @click="goToWorkbench(project.id)"
        >
          <div class="card-header">
            <h3 class="project-title">{{ project.title }}</h3>
            <el-dropdown @click.stop trigger="click" @command="(cmd: string) => handleCommand(cmd, project)">
              <el-button text size="small" class="more-btn" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="edit">
                    <el-icon><Edit /></el-icon> 进入创作
                  </el-dropdown-item>
                  <el-dropdown-item command="export-txt">
                    <el-icon><Download /></el-icon> 导出 TXT
                  </el-dropdown-item>
                  <el-dropdown-item command="export-md">
                    <el-icon><Document /></el-icon> 导出 Markdown
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon> 删除项目
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <p class="project-description">{{ project.description || '暂无简介' }}</p>

          <div class="project-meta">
            <span class="genre-tag" v-if="project.genre">
              <el-icon><Collection /></el-icon>
              {{ project.genre }}
            </span>
            <el-tag :type="statusTagType(project.status)" size="small" effect="plain">
              {{ statusLabel(project.status) }}
            </el-tag>
          </div>

          <!-- 字数进度 -->
          <div class="word-count-section">
            <div class="word-count-labels">
              <span class="current-words">{{ project.current_word_count.toLocaleString() }} 字</span>
              <span class="target" v-if="project.target_word_count > 0">
                / {{ project.target_word_count.toLocaleString() }}
              </span>
            </div>
            <el-progress
              v-if="project.target_word_count > 0"
              :percentage="wordCountPercentage(project)"
              :color="progressColor"
              :stroke-width="4"
              :show-text="false"
            />
          </div>

          <!-- 时间信息 -->
          <div class="card-footer">
            <span class="create-time" :title="'创建于 ' + formatDate(project.created_at)">
              <el-icon><Clock /></el-icon>
              {{ formatRelativeDate(project.updated_at || project.created_at) }}
            </span>
          </div>
        </el-card>
      </div>
    </main>

    <!-- 新建项目对话框 -->
    <el-dialog
      :close-on-press-escape="false"
      v-model="showCreateDialog"
      title="新建项目"
      width="520px"
      :close-on-click-modal="false"
    >
      <el-form
        ref="createFormRef"
        :model="createForm"
        :rules="createRules"
        label-width="100px"
        label-position="left"
      >
        <el-form-item label="项目标题" prop="title">
          <el-input v-model="createForm.title" placeholder="请输入项目标题" maxlength="100" />
        </el-form-item>

        <el-form-item label="简介">
          <el-input
            v-model="createForm.description"
            type="textarea"
            :rows="3"
            placeholder="简短描述你的故事..."
            maxlength="500"
          />
        </el-form-item>

        <el-form-item label="类型">
          <el-select v-model="createForm.genre" placeholder="选择小说类型" style="width: 100%">
            <el-option label="奇幻" value="奇幻" />
            <el-option label="科幻" value="科幻" />
            <el-option label="玄幻" value="玄幻" />
            <el-option label="言情" value="言情" />
            <el-option label="悬疑" value="悬疑" />
            <el-option label="历史" value="历史" />
            <el-option label="武侠" value="武侠" />
            <el-option label="都市" value="都市" />
            <el-option label="恐怖" value="恐怖" />
            <el-option label="军事" value="军事" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>

        <el-form-item label="目标字数">
          <el-input-number
            v-model="createForm.target_word_count"
            :min="0"
            :max="10000000"
            :step="10000"
            style="width: 100%"
          />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建项目</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Edit, Delete, Collection, MoreFilled, Download, Document, Clock } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { Project } from '@/api/project'

const router = useRouter()
const projectStore = useProjectStore()

const showCreateDialog = ref(false)
const creating = ref(false)
const createFormRef = ref<FormInstance>()

const createForm = ref({
  title: '',
  description: '',
  genre: '',
  target_word_count: 100000,
})

const createRules: FormRules = {
  title: [{ required: true, message: '请输入项目标题', trigger: 'blur' }],
}

const progressColor = '#6B7B8D'

// 统计数据
const totalWords = computed(() =>
  projectStore.projects.reduce((sum, p) => sum + (p.current_word_count || 0), 0)
)
const writingCount = computed(() =>
  projectStore.projects.filter(p => p.status === 'draft' || p.status === 'writing').length
)
const completedCount = computed(() =>
  projectStore.projects.filter(p => p.status === 'completed').length
)

function statusTagType(status: string) {
  const map: Record<string, string> = {
    draft: 'info', planning: 'info', writing: 'success', completed: 'warning', archived: 'danger',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    draft: '草稿', planning: '规划中', writing: '创作中', completed: '已完成', archived: '已归档',
  }
  return map[status] || status
}

function wordCountPercentage(project: Project) {
  if (!project.target_word_count) return 0
  return Math.min(Math.round((project.current_word_count / project.target_word_count) * 100), 100)
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatRelativeDate(dateStr: string) {
  const d = new Date(dateStr)
  const now = new Date()
  const diff = now.getTime() - d.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return formatDate(dateStr)
}

function goToWorkbench(id: number) {
  router.push(`/project/${id}`)
}

function goToWizard() {
  router.push('/wizard')
}

function handleCommand(command: string, project: Project) {
  switch (command) {
    case 'edit':
      goToWorkbench(project.id)
      break
    case 'export-txt':
      exportProject(project.id, 'txt')
      break
    case 'export-md':
      exportProject(project.id, 'markdown')
      break
    case 'delete':
      handleDelete(project)
      break
  }
}

async function exportProject(id: number, format: string) {
  try {
    const url = `/api/v1/projects/${id}/export/${format}`
    const resp = await fetch(url)
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    const ext = format === 'markdown' ? 'md' : 'txt'
    const project = projectStore.projects.find(p => p.id === id)
    const title = project?.title || '导出'
    a.download = `${title}.${ext}`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function handleCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    creating.value = true
    try {
      const project = await projectStore.createNewProject(createForm.value)
      showCreateDialog.value = false
      createForm.value = { title: '', description: '', genre: '', target_word_count: 100000 }
      router.push(`/project/${project.id}`)
    } finally {
      creating.value = false
    }
  })
}

async function handleDelete(project: Project) {
  await ElMessageBox.confirm(`确定要删除《${project.title}》吗？此操作不可撤销。`, '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
  })
  await projectStore.removeProject(project.id)
}

onMounted(() => {
  projectStore.fetchProjects()
})
</script>

<style scoped>
.project-list-page {
  min-height: 100vh;
  background-color: #F0EFEC;
}

.page-header {
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  box-shadow: 0 1px 3px rgba(44, 44, 44, 0.03);
}

.header-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-icon {
  font-size: 24px;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
}

.page-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

/* 统计栏 */
.stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 32px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  padding: 20px 24px;
  background: white;
  border-radius: 14px;
  box-shadow: 0 1px 3px rgba(44, 44, 44, 0.04);
  transition: all 0.2s ease;
}

.stat-item:hover {
  box-shadow: 0 4px 12px rgba(44, 44, 44, 0.05);
  transform: translateY(-2px);
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
}

.stat-label {
  font-size: 12px;
  color: #9E9E9E;
  margin-top: 4px;
}

/* 空状态 */
.empty-state {
  padding: 100px 0;
  text-align: center;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.empty-title {
  font-size: 24px;
  color: #2C2C2C;
  margin-bottom: 8px;
  font-family: 'Noto Serif SC', serif;
}

.empty-desc {
  font-size: 14px;
  color: #9E9E9E;
  margin-bottom: 24px;
}

.loading-container {
  padding: 24px;
  background: white;
  border-radius: 14px;
}

/* 项目网格 */
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 20px;
}

.project-card {
  cursor: pointer;
  background-color: white !important;
  border: 1px solid #E0DFDC !important;
  transition: all 0.25s ease;
  border-radius: 14px !important;
}

.project-card:hover {
  border-color: #6B7B8D !important;
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(107, 123, 141, 0.10) !important;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}

.project-title {
  font-size: 17px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
  flex: 1;
  margin-right: 8px;
  font-family: 'Noto Serif SC', serif;
}

.more-btn {
  color: #9E9E9E !important;
}

.more-btn:hover {
  color: #6B7B8D !important;
}

.project-description {
  font-size: 13px;
  color: #7A7A7A;
  line-height: 1.6;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
}

.genre-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #6B7B8D;
  background: rgba(107, 123, 141, 0.08);
  padding: 2px 10px;
  border-radius: 14px;
}

.word-count-section {
  margin-bottom: 12px;
}

.word-count-labels {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin-bottom: 6px;
}

.current-words {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
}

.target {
  font-size: 12px;
  color: #9E9E9E;
}

.card-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 10px;
  border-top: 1px solid #ECEAE6;
}

.create-time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: #9E9E9E;
}

/* 响应式适配 */
@media (max-width: 768px) {
  .page-main {
    padding: 16px;
  }

  .stats-bar {
    flex-wrap: wrap;
    gap: 8px;
  }

  .stat-item {
    flex: 1 1 45%;
    padding: 12px 16px;
  }

  .projects-grid {
    grid-template-columns: 1fr;
  }

  .header-content {
    padding: 0 16px;
  }
}
</style>
