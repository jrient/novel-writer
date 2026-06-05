<template>
  <div class="dashboard-page">
    <!-- 顶部栏 -->
    <header class="page-header">
      <div class="header-content">
        <div class="logo-area">
          <span class="logo-icon">&#9997;</span>
          <h1 class="logo">AI小说创作平台</h1>
        </div>
        <div class="header-actions">
          <ThemeToggle />
          <el-button
            v-if="userStore.is_superuser"
            @click="$router.push('/admin')"
            round
          >
            管理后台
          </el-button>
          <el-button type="primary" :icon="Plus" @click="goToWizard" round>
            新建项目
          </el-button>
        </div>
      </div>
    </header>

    <main class="page-main">
      <!-- 欢迎语 -->
      <div class="welcome">
        <h2 class="welcome-title">{{ greeting }}，欢迎回来</h2>
        <p class="welcome-sub">选择一个工作区，开始你的创作。</p>
      </div>

      <!-- 统计条 -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-value">{{ projectStore.projects.length }}</span>
          <span class="stat-label">项目总数</span>
        </div>
        <div class="stat-item">
          <span class="stat-value">{{ totalWords.toLocaleString() }}</span>
          <span class="stat-label">累计字数</span>
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

      <!-- 最近项目 -->
      <section class="section" v-if="recentProjects.length > 0">
        <div class="section-head">
          <h3 class="section-title">最近编辑</h3>
          <el-button text class="more-link" @click="$router.push('/projects')">
            查看全部<el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
        <div class="recent-grid">
          <div
            v-for="p in recentProjects"
            :key="p.id"
            class="recent-card"
            @click="goToWorkbench(p.id)"
          >
            <div class="recent-top">
              <h4 class="recent-title">{{ p.title }}</h4>
              <el-tag :type="statusTagType(p.status)" size="small" effect="plain">
                {{ statusLabel(p.status) }}
              </el-tag>
            </div>
            <p class="recent-desc">{{ p.description || '暂无简介' }}</p>
            <div class="recent-foot">
              <span class="recent-words">{{ p.current_word_count.toLocaleString() }} 字</span>
              <span class="recent-time">
                <el-icon><Clock /></el-icon>
                {{ formatRelativeDate(p.updated_at || p.created_at) }}
              </span>
            </div>
          </div>
        </div>
      </section>

      <!-- 功能分组 -->
      <section
        v-for="group in featureGroups"
        :key="group.title"
        class="section"
      >
        <div class="section-head">
          <h3 class="section-title">{{ group.title }}</h3>
          <span class="section-hint">{{ group.hint }}</span>
        </div>
        <div class="feature-grid">
          <div
            v-for="f in group.items"
            :key="f.label"
            class="feature-card"
            :style="{ '--accent': f.color }"
            @click="$router.push(f.to)"
          >
            <div class="feature-icon">
              <el-icon><component :is="f.icon" /></el-icon>
            </div>
            <div class="feature-body">
              <span class="feature-label">{{ f.label }}</span>
              <span class="feature-desc">{{ f.desc }}</span>
            </div>
            <el-icon class="feature-arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, markRaw } from 'vue'
import { useRouter } from 'vue-router'
import {
  Plus, ArrowRight, Clock, Notebook, MagicStick, Film,
  Star, Edit, DocumentCopy, Reading, Collection,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/project'
import { useUserStore } from '@/stores/user'
import ThemeToggle from '@/components/ThemeToggle.vue'

const router = useRouter()
const projectStore = useProjectStore()
const userStore = useUserStore()

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

const totalWords = computed(() =>
  projectStore.projects.reduce((sum, p) => sum + (p.current_word_count || 0), 0)
)
const writingCount = computed(() =>
  projectStore.projects.filter(p => p.status === 'draft' || p.status === 'writing').length
)
const completedCount = computed(() =>
  projectStore.projects.filter(p => p.status === 'completed').length
)

const recentProjects = computed(() =>
  [...projectStore.projects]
    .sort((a, b) =>
      new Date(b.updated_at || b.created_at).getTime() -
      new Date(a.updated_at || a.created_at).getTime()
    )
    .slice(0, 4)
)

const featureGroups = [
  {
    title: '小说创作',
    hint: '从灵感到成稿',
    items: [
      { label: '我的项目', desc: '管理与续写长篇小说', icon: markRaw(Notebook), color: '#6B7B8D', to: '/projects' },
      { label: '创作向导', desc: '一步步引导生成新书', icon: markRaw(MagicStick), color: '#7A8FA6', to: '/wizard' },
    ],
  },
  {
    title: '剧本工作室',
    hint: '短剧 / 剧本全流程',
    items: [
      { label: '剧本创作', desc: 'AI 引导生成剧本', icon: markRaw(Film), color: '#9A7B8D', to: '/drama' },
      { label: '剧本评分', desc: '按评分卡量化打分', icon: markRaw(Star), color: '#C2964A', to: '/rubric/score' },
      { label: '剧本改编', desc: '小说 / 文本改编为剧本', icon: markRaw(Edit), color: '#7B9A8D', to: '/adaptation' },
    ],
  },
  {
    title: '智能加工 · 资源',
    hint: '文本处理与素材库',
    items: [
      { label: '原作知识图谱', desc: '上传小说、查看设定与关系图谱', icon: markRaw(Collection), color: '#5B8FF9', to: '/reference-library' },
      { label: '文本扩写', desc: '细纲扩写为正文', icon: markRaw(DocumentCopy), color: '#6B8D9A', to: '/expansion' },
      { label: '散文改写', desc: '风格化散文改写', icon: markRaw(Reading), color: '#8D7B9A', to: '/prose' },
      { label: '风格样本库', desc: '管理文风参考样本', icon: markRaw(Collection), color: '#9E9E9E', to: '/style-samples' },
    ],
  },
]

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

function goToWorkbench(id: number) {
  router.push(`/project/${id}`)
}
function goToWizard() {
  router.push('/wizard')
}

onMounted(() => {
  projectStore.fetchProjects()
})
</script>

<style scoped>
.dashboard-page {
  min-height: 100vh;
  background-color: var(--writer-bg-main);
}

/* 顶部栏 */
.page-header {
  background-color: var(--writer-bg-card);
  border-bottom: 1px solid var(--writer-border);
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  z-index: 10;
}
.header-content {
  width: 100%;
  max-width: 1160px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
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
  background: linear-gradient(135deg, var(--writer-primary) 0%, var(--writer-primary-dark) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
}

.page-main {
  max-width: 1160px;
  margin: 0 auto;
  padding: 32px;
}

/* 欢迎语 */
.welcome {
  margin-bottom: 24px;
}
.welcome-title {
  font-size: 26px;
  font-weight: 700;
  color: var(--writer-text-main);
  font-family: 'Noto Serif SC', serif;
  margin-bottom: 4px;
}
.welcome-sub {
  font-size: 14px;
  color: var(--writer-text-muted);
}

/* 统计条 */
.stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 36px;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  padding: 18px 24px;
  background: var(--writer-bg-card);
  border: 1px solid var(--writer-border);
  border-radius: 14px;
  transition: all 0.2s ease;
}
.stat-item:hover {
  box-shadow: 0 4px 12px rgba(44, 44, 44, 0.05);
  transform: translateY(-2px);
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--writer-primary) 0%, var(--writer-primary-dark) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
}
.stat-label {
  font-size: 12px;
  color: var(--writer-text-muted);
  margin-top: 4px;
}

/* 区块 */
.section {
  margin-bottom: 36px;
}
.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
}
.section-title {
  font-size: 17px;
  font-weight: 600;
  color: var(--writer-text-main);
  font-family: 'Noto Serif SC', serif;
  position: relative;
  padding-left: 12px;
}
.section-title::before {
  content: '';
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 4px;
  height: 16px;
  border-radius: 2px;
  background: var(--writer-primary);
}
.section-hint {
  font-size: 12px;
  color: var(--writer-text-muted);
}
.more-link {
  color: var(--writer-text-secondary) !important;
  font-size: 13px;
}
.more-link:hover {
  color: var(--writer-primary) !important;
}

/* 最近项目 */
.recent-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.recent-card {
  background: var(--writer-bg-card);
  border: 1px solid var(--writer-border);
  border-radius: 14px;
  padding: 16px 18px;
  cursor: pointer;
  transition: all 0.25s ease;
}
.recent-card:hover {
  border-color: var(--writer-primary);
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(107, 123, 141, 0.10);
}
.recent-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.recent-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--writer-text-main);
  font-family: 'Noto Serif SC', serif;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.recent-desc {
  font-size: 12px;
  color: var(--writer-text-muted);
  line-height: 1.6;
  height: 38px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: 10px;
}
.recent-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid var(--writer-border-light);
}
.recent-words {
  font-size: 13px;
  font-weight: 600;
  color: var(--writer-text-secondary);
}
.recent-time {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--writer-text-muted);
}

/* 功能卡 */
.feature-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}
.feature-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--writer-bg-card);
  border: 1px solid var(--writer-border);
  border-radius: 14px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.25s ease;
}
.feature-card:hover {
  border-color: var(--accent);
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(44, 44, 44, 0.08);
}
.feature-icon {
  flex-shrink: 0;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
}
.feature-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}
.feature-label {
  font-size: 15px;
  font-weight: 600;
  color: var(--writer-text-main);
  font-family: 'Noto Serif SC', serif;
}
.feature-desc {
  font-size: 12px;
  color: var(--writer-text-muted);
  margin-top: 2px;
}
.feature-arrow {
  color: var(--writer-text-light);
  font-size: 16px;
  transition: all 0.25s ease;
}
.feature-card:hover .feature-arrow {
  color: var(--accent);
  transform: translateX(3px);
}

/* 响应式 */
@media (max-width: 768px) {
  .page-header { padding: 0 16px; }
  .page-main { padding: 16px; }
  .header-actions { gap: 6px; }
  .stats-bar { flex-wrap: wrap; gap: 8px; }
  .stat-item { flex: 1 1 45%; padding: 12px 16px; }
  .recent-grid, .feature-grid { grid-template-columns: 1fr; }
}
</style>
