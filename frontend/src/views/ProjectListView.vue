<template>
  <div class="project-list-page">
    <!-- 顶部导航栏 -->
    <header class="page-header">
      <div class="header-content">
        <h1 class="logo">AI小说创作平台</h1>
        <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
          新建项目
        </el-button>
      </div>
    </header>

    <!-- 主体内容 -->
    <main class="page-main">
      <!-- 加载状态 -->
      <div v-if="projectStore.loading" class="loading-container">
        <el-skeleton :rows="3" animated />
      </div>

      <!-- 空状态 -->
      <div v-else-if="projectStore.projects.length === 0" class="empty-state">
        <el-empty description="还没有项目，点击右上角新建一个吧">
          <el-button type="primary" @click="showCreateDialog = true">创建第一个项目</el-button>
        </el-empty>
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
            <el-tag :type="statusTagType(project.status)" size="small">
              {{ statusLabel(project.status) }}
            </el-tag>
          </div>

          <p class="project-description">{{ project.description || '暂无简介' }}</p>

          <div class="project-meta">
            <span class="genre-tag" v-if="project.genre">
              <el-icon><Collection /></el-icon>
              {{ project.genre }}
            </span>
          </div>

          <!-- 字数进度 -->
          <div class="word-count-section">
            <div class="word-count-labels">
              <span>{{ project.current_word_count.toLocaleString() }} 字</span>
              <span class="target">目标 {{ project.target_word_count.toLocaleString() }} 字</span>
            </div>
            <el-progress
              :percentage="wordCountPercentage(project)"
              :color="progressColor"
              :stroke-width="6"
              :show-text="false"
            />
          </div>

          <!-- 操作按钮 -->
          <div class="card-actions" @click.stop>
            <el-button size="small" text @click="goToWorkbench(project.id)">
              <el-icon><Edit /></el-icon> 进入创作
            </el-button>
            <el-button size="small" text type="danger" @click="handleDelete(project)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
        </el-card>
      </div>
    </main>

    <!-- 新建项目对话框 -->
    <el-dialog
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
            <el-option label="言情" value="言情" />
            <el-option label="悬疑" value="悬疑" />
            <el-option label="历史" value="历史" />
            <el-option label="武侠" value="武侠" />
            <el-option label="都市" value="都市" />
            <el-option label="其他" value="其他" />
          </el-select>
        </el-form-item>

        <el-form-item label="目标字数">
          <el-input-number
            v-model="createForm.target_word_count"
            :min="1000"
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
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { Plus, Edit, Delete, Collection } from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import type { Project } from '@/api/project'

const router = useRouter()
const projectStore = useProjectStore()

// 对话框控制
const showCreateDialog = ref(false)
const creating = ref(false)
const createFormRef = ref<FormInstance>()

// 创建表单数据
const createForm = ref({
  title: '',
  description: '',
  genre: '',
  target_word_count: 100000,
})

// 表单验证规则
const createRules: FormRules = {
  title: [{ required: true, message: '请输入项目标题', trigger: 'blur' }],
}

// 进度条颜色（金色主题）
const progressColor = '#e2b714'

// 状态标签类型映射
function statusTagType(status: string) {
  const map: Record<string, string> = {
    planning: 'info',
    writing: 'success',
    completed: 'warning',
    archived: 'danger',
  }
  return map[status] || 'info'
}

// 状态中文标签
function statusLabel(status: string) {
  const map: Record<string, string> = {
    planning: '规划中',
    writing: '创作中',
    completed: '已完成',
    archived: '已归档',
  }
  return map[status] || status
}

// 计算字数完成百分比
function wordCountPercentage(project: Project) {
  if (!project.target_word_count) return 0
  return Math.min(
    Math.round((project.current_word_count / project.target_word_count) * 100),
    100
  )
}

// 跳转到工作台
function goToWorkbench(id: number) {
  router.push(`/project/${id}`)
}

// 创建项目
async function handleCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    creating.value = true
    try {
      const project = await projectStore.createNewProject(createForm.value)
      showCreateDialog.value = false
      // 重置表单
      createForm.value = { title: '', description: '', genre: '', target_word_count: 100000 }
      // 跳转到新项目工作台
      router.push(`/project/${project.id}`)
    } finally {
      creating.value = false
    }
  })
}

// 删除项目确认
async function handleDelete(project: Project) {
  await ElMessageBox.confirm(`确定要删除《${project.title}》吗？此操作不可撤销。`, '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
  })
  await projectStore.removeProject(project.id)
}

// 页面挂载时加载项目列表
onMounted(() => {
  projectStore.fetchProjects()
})
</script>

<style scoped>
.project-list-page {
  min-height: 100vh;
  background-color: #1a1a2e;
}

/* 顶部导航 */
.page-header {
  background-color: #16213e;
  border-bottom: 1px solid #2d3561;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
}

.header-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  color: #e2b714;
  font-family: 'Noto Serif SC', serif;
}

/* 主体 */
.page-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

.loading-container {
  padding: 24px;
}

.empty-state {
  padding: 80px 0;
  text-align: center;
}

/* 项目网格 */
.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

/* 项目卡片 */
.project-card {
  cursor: pointer;
  background-color: #16213e !important;
  border: 1px solid #2d3561 !important;
  transition: border-color 0.2s, transform 0.2s;
}

.project-card:hover {
  border-color: #e2b714 !important;
  transform: translateY(-2px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.project-title {
  font-size: 16px;
  font-weight: 600;
  color: #e0e0e0;
  margin: 0;
  flex: 1;
  margin-right: 8px;
}

.project-description {
  font-size: 13px;
  color: #909399;
  line-height: 1.6;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.project-meta {
  margin-bottom: 12px;
}

.genre-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #e2b714;
  background: rgba(226, 183, 20, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
}

.word-count-section {
  margin-bottom: 16px;
}

.word-count-labels {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
}

.target {
  color: #606266;
}

.card-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid #2d3561;
}

/* 对话框暗色主题覆盖 */
:deep(.el-dialog) {
  background-color: #16213e;
  border: 1px solid #2d3561;
}

:deep(.el-dialog__title) {
  color: #e0e0e0;
}

:deep(.el-form-item__label) {
  color: #c0c4cc;
}

:deep(.el-input__wrapper) {
  background-color: #1a1a2e;
  border-color: #2d3561;
}

:deep(.el-input__inner) {
  color: #e0e0e0;
}

:deep(.el-textarea__inner) {
  background-color: #1a1a2e;
  color: #e0e0e0;
  border-color: #2d3561;
}
</style>
