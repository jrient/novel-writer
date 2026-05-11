<template>
  <div class="adaptation-list">
    <div class="header">
      <h2>我的剧本改编</h2>
      <el-button type="primary" @click="$router.push('/adaptation/create')">
        新建改编
      </el-button>
    </div>

    <el-empty v-if="!loading && projects.length === 0" description="还没有改编项目" />

    <div class="cards">
      <el-card
        v-for="p in projects"
        :key="p.id"
        class="card"
        shadow="hover"
        @click="$router.push(`/adaptation/workbench/${p.id}`)"
      >
        <div class="card-title">{{ p.title }}</div>
        <div class="card-meta">
          <el-tag size="small">强度 {{ p.intensity }}</el-tag>
          <el-tag size="small" :type="statusTag(p.status)">{{ p.status }}</el-tag>
          <span class="version-no">v{{ latestVersion(p) }}</span>
        </div>
        <div class="card-foot">
          <span>{{ p.word_count }} 字</span>
          <span>{{ formatTime(p.created_at) }}</span>
          <el-button type="danger" link size="small" @click.stop="confirmDelete(p)">删除</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adaptationApi, type AdaptationProject } from '@/api/adaptation'

const projects = ref<AdaptationProject[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await adaptationApi.list()
    projects.value = r as any
  } finally {
    loading.value = false
  }
}

function latestVersion(p: AdaptationProject) {
  return p.versions.length ? Math.max(...p.versions.map(v => v.version_no)) : '-'
}

function statusTag(s: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  if (s === 'done') return 'success'
  if (s === 'generating' || s === 'extracting') return 'warning'
  if (s.endsWith('_failed') || s === 'failed') return 'danger'
  return ''
}

function formatTime(s: string) {
  return new Date(s).toLocaleString()
}

async function confirmDelete(p: AdaptationProject) {
  await ElMessageBox.confirm(`删除「${p.title}」？此操作不可撤销。`, '确认', {type: 'warning'})
  await adaptationApi.remove(p.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.adaptation-list { padding: 24px; max-width: 1200px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card { cursor: pointer; }
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.card-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.version-no { color: #909399; font-size: 12px; }
.card-foot { display: flex; justify-content: space-between; color: #909399; font-size: 12px; align-items: center; }
</style>
