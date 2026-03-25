<template>
  <div class="drama-list-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.push('/projects')">返回项目</el-button>
          <div class="logo-area">
            <span class="logo-icon">&#127916;</span>
            <h1 class="logo">剧本创作</h1>
          </div>
        </div>
        <el-button type="primary" :icon="Plus" @click="router.push('/drama/create')" round>
          新建剧本
        </el-button>
      </div>
    </header>

    <main class="page-main">
      <!-- Filter tabs -->
      <div class="filter-bar">
        <el-radio-group v-model="filterType" size="small" @change="handleFilterChange">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="explanatory">解说漫</el-radio-button>
          <el-radio-button value="dynamic">动态漫</el-radio-button>
        </el-radio-group>
      </div>

      <!-- Loading -->
      <div v-if="dramaStore.loading" class="loading-container">
        <el-skeleton :rows="3" animated />
      </div>

      <!-- Empty state -->
      <div v-else-if="!filteredProjects.length" class="empty-state">
        <div class="empty-icon">&#127916;</div>
        <h2 class="empty-title">还没有剧本项目</h2>
        <p class="empty-desc">点击下方按钮创建第一个剧本</p>
        <el-button type="primary" size="large" @click="router.push('/drama/create')" round>
          创建第一个剧本
        </el-button>
      </div>

      <!-- Project grid -->
      <div v-else class="projects-grid">
        <el-card
          v-for="project in filteredProjects"
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

          <div class="card-tags">
            <el-tag
              :type="project.script_type === 'explanatory' ? 'success' : 'primary'"
              size="small"
              effect="light"
            >
              {{ project.script_type === 'explanatory' ? '解说漫' : '动态漫' }}
            </el-tag>
            <el-tag :type="statusTagType(project.status)" size="small" effect="plain">
              {{ statusLabel(project.status) }}
            </el-tag>
          </div>

          <p class="project-concept">{{ project.concept || '暂无创意描述' }}</p>

          <div class="card-footer">
            <span class="create-time">
              <el-icon><Clock /></el-icon>
              {{ formatRelativeDate(project.updated_at || project.created_at) }}
            </span>
          </div>
        </el-card>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowLeft, Plus, Edit, Delete, MoreFilled, Download, Document, Clock } from '@element-plus/icons-vue'
import { useDramaStore } from '@/stores/drama'
import { getExportUrl } from '@/api/drama'
import type { ScriptProjectListItem } from '@/api/drama'

const router = useRouter()
const dramaStore = useDramaStore()

const filterType = ref('')

const filteredProjects = computed(() => {
  if (!filterType.value) return dramaStore.projects
  return dramaStore.projects.filter(p => p.script_type === filterType.value)
})

function statusTagType(status: string) {
  const map: Record<string, 'info' | 'success' | 'warning' | 'danger'> = {
    drafting: 'info',
    outlined: 'warning',
    writing: 'success',
    completed: 'warning',
  }
  return map[status] || 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    drafting: '草稿',
    outlined: '已大纲',
    writing: '创作中',
    completed: '已完成',
  }
  return map[status] || status
}

function formatDate(dateStr: string) {
  const d = new Date(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatRelativeDate(dateStr: string) {
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

function openProject(project: ScriptProjectListItem) {
  if (project.status === 'drafting') {
    router.push(`/drama/wizard/${project.id}`)
  } else {
    router.push(`/drama/workbench/${project.id}`)
  }
}

function handleCommand(command: string, project: ScriptProjectListItem) {
  switch (command) {
    case 'open':
      openProject(project)
      break
    case 'export-txt':
      downloadExport(project.id, 'txt', project.title)
      break
    case 'export-md':
      downloadExport(project.id, 'markdown', project.title)
      break
    case 'delete':
      handleDelete(project)
      break
  }
}

async function downloadExport(id: number, format: 'txt' | 'markdown', title: string) {
  try {
    const url = getExportUrl(id, format)
    const token = localStorage.getItem('access_token')
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch(url, { headers })
    if (!resp.ok) throw new Error('导出失败')
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${title}.${format === 'markdown' ? 'md' : 'txt'}`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

async function handleDelete(project: ScriptProjectListItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除《${project.title}》吗？此操作不可撤销。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '确认删除', cancelButtonText: '取消' },
    )
    await dramaStore.removeProject(project.id)
    ElMessage.success('已删除')
  } catch {
    // cancelled
  }
}

function handleFilterChange() {
  dramaStore.fetchProjects(filterType.value ? { script_type: filterType.value } : undefined)
}

onMounted(() => {
  dramaStore.fetchProjects()
})
</script>

<style scoped>
.drama-list-page {
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
  gap: 6px;
  margin-bottom: 10px;
}

.project-concept {
  font-size: 13px;
  color: #7A7A7A;
  line-height: 1.6;
  margin-bottom: 12px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
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

:deep(.el-radio-button__inner) {
  border-color: #E0DFDC;
  color: #5C5C5C;
}

:deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  border-color: transparent;
  color: white;
  box-shadow: none;
}

@media (max-width: 768px) {
  .page-main { padding: 16px; }
  .projects-grid { grid-template-columns: 1fr; }
  .page-header { padding: 0 16px; }
}
</style>
