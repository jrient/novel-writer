<template>
  <div class="expansion-list-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.push('/projects')">返回项目</el-button>
          <div class="logo-area">
            <span class="logo-icon">&#128221;</span>
            <h1 class="logo">文本扩写</h1>
          </div>
        </div>
        <el-button type="primary" :icon="Plus" @click="router.push('/expansion/create')" round>
          新建扩写
        </el-button>
      </div>
    </header>

    <main class="page-main">
      <!-- Filter bar -->
      <div class="filter-bar">
        <el-select v-model="filterStatus" placeholder="全部状态" clearable size="small" @change="handleFilterChange">
          <el-option label="全部状态" value="" />
          <el-option label="已创建" value="created" />
          <el-option label="已分析" value="analyzed" />
          <el-option label="已分段" value="segmented" />
          <el-option label="扩写中" value="expanding" />
          <el-option label="已暂停" value="paused" />
          <el-option label="出错" value="error" />
          <el-option label="已完成" value="completed" />
        </el-select>
      </div>

      <!-- Loading -->
      <div v-if="expansionStore.loading" class="loading-container">
        <el-skeleton :rows="3" animated />
      </div>

      <!-- Empty state -->
      <div v-else-if="!expansionStore.projects.length" class="empty-state">
        <div class="empty-icon">&#128221;</div>
        <h2 class="empty-title">还没有扩写项目</h2>
        <p class="empty-desc">点击下方按钮创建第一个扩写项目</p>
        <el-button type="primary" size="large" @click="router.push('/expansion/create')" round>
          创建第一个扩写
        </el-button>
      </div>

      <!-- Project grid -->
      <div v-else class="projects-grid">
        <el-card
          v-for="project in expansionStore.projects"
          :key="project.id"
          class="project-card"
          shadow="hover"
          @click="openProject(project)"
        >
          <div class="card-header">
            <h3 class="project-title">{{ project.title }}</h3>
            <el-dropdown trigger="click" @click.stop @command="(cmd: string) => handleCommand(cmd, project)">
              <el-button text size="small" class="more-btn" @click.stop>
                <el-icon><MoreFilled /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="open">
                    <el-icon><Edit /></el-icon> 打开项目
                  </el-dropdown-item>
                  <el-dropdown-item command="delete" divided>
                    <el-icon><Delete /></el-icon> 删除项目
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>

          <div class="card-tags">
            <el-tag :type="sourceTypeTagType(project.source_type)" size="small" effect="light">
              {{ sourceTypeLabel(project.source_type) }}
            </el-tag>
            <el-tag :type="statusTagType(project.status)" size="small" effect="plain">
              {{ statusLabel(project.status) }}
            </el-tag>
            <el-tag type="info" size="small" effect="plain">
              {{ project.expansion_level === 'light' ? '轻度' : project.expansion_level === 'medium' ? '中度' : '深度' }}
            </el-tag>
          </div>

          <div class="project-stats">
            <span class="stat-item">
              <el-icon><Document /></el-icon>
              {{ project.word_count.toLocaleString() }} 字
            </span>
          </div>

          <div class="card-footer">
            <span class="create-time">
              <el-icon><Clock /></el-icon>
              {{ formatRelativeDate(project.created_at) }}
            </span>
          </div>
        </el-card>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Edit, Delete, MoreFilled, Document, Clock } from '@element-plus/icons-vue'
import { useExpansionStore } from '@/stores/expansion'
import type { ExpansionProjectListItem } from '@/api/expansion'

const router = useRouter()
const expansionStore = useExpansionStore()

const filterStatus = ref('')

function sourceTypeTagType(type: string): 'primary' | 'success' | 'warning' | 'info' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info'> = {
    upload: 'primary',
    novel: 'success',
    drama: 'warning',
    manual: 'info',
  }
  return map[type] || 'info'
}

function sourceTypeLabel(type: string): string {
  const map: Record<string, string> = {
    upload: '上传文件',
    novel: '小说导入',
    drama: '剧本导入',
    manual: '手动输入',
  }
  return map[type] || type
}

function statusTagType(status: string): 'info' | 'success' | 'warning' | 'danger' {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    created: 'info',
    analyzed: 'info',
    segmented: 'warning',
    expanding: 'success',
    paused: 'warning',
    error: 'danger',
    completed: 'success',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    created: '已创建',
    analyzed: '已分析',
    segmented: '已分段',
    expanding: '扩写中',
    paused: '已暂停',
    error: '出错',
    completed: '已完成',
  }
  return map[status] || status
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatRelativeDate(dateStr: string): string {
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  if (hours < 24) return `${hours} 小时前`
  if (days < 7) return `${days} 天前`
  return formatDate(dateStr)
}

function openProject(project: ExpansionProjectListItem) {
  // If status is created or analyzed, go to analyze page
  // Otherwise go to workbench
  if (project.status === 'created' || project.status === 'analyzed') {
    router.push(`/expansion/analyze/${project.id}`)
  } else {
    router.push(`/expansion/workbench/${project.id}`)
  }
}

function handleCommand(command: string, project: ExpansionProjectListItem) {
  switch (command) {
    case 'open':
      openProject(project)
      break
    case 'delete':
      handleDelete(project)
      break
  }
}

async function handleDelete(project: ExpansionProjectListItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除《${project.title}》吗？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await expansionStore.removeProject(project.id)
    ElMessage.success('已删除')
  } catch {
    // cancelled
  }
}

function handleFilterChange() {
  expansionStore.fetchProjects(filterStatus.value ? { status: filterStatus.value } : undefined)
}

onMounted(() => {
  expansionStore.fetchProjects()
})
</script>

<style scoped>
.expansion-list-page {
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

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 8px;
}

.logo-icon {
  font-size: 22px;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
  margin: 0;
}

.page-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

.filter-bar {
  margin-bottom: 24px;
}

.loading-container {
  padding: 24px;
  background: white;
  border-radius: 14px;
}

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

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
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

.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 10px;
}

.project-stats {
  display: flex;
  gap: 16px;
  margin-bottom: 10px;
}

.stat-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #7A7A7A;
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

@media (max-width: 768px) {
  .page-main { padding: 16px; }
  .projects-grid { grid-template-columns: 1fr; }
  .page-header { padding: 0 16px; }
}
</style>