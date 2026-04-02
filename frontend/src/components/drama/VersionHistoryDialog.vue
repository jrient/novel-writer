<template>
  <el-dialog
    v-model="visible"
    title="历史版本"
    width="640px"
    :close-on-click-modal="false"
    @open="loadVersions"
  >
    <div v-loading="loading" class="version-list">
      <el-empty v-if="!loading && !versions.length" description="暂无历史版本" :image-size="60" />

      <div
        v-for="ver in versions"
        :key="ver.id"
        class="version-item"
        :class="{ 'version-item--active': expandedId === ver.id }"
      >
        <div class="version-header" @click="toggleExpand(ver)">
          <div class="version-meta">
            <span class="version-number">v{{ ver.version_number }}</span>
            <el-tag :type="sourceTagType(ver.source)" size="small" effect="plain">
              {{ sourceLabel(ver.source) }}
            </el-tag>
            <span class="version-title">{{ ver.title || '(无标题)' }}</span>
          </div>
          <span class="version-time">{{ formatTime(ver.created_at) }}</span>
        </div>

        <div v-if="expandedId === ver.id" class="version-content">
          <pre class="content-preview">{{ ver.content || '(空内容)' }}</pre>
          <div class="version-actions">
            <el-button
              type="primary"
              size="small"
              :loading="restoring"
              @click="handleRestore(ver)"
            >
              恢复此版本
            </el-button>
          </div>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listNodeVersions, restoreNodeVersion } from '@/api/drama'
import type { NodeVersion } from '@/api/drama'

const props = defineProps<{
  projectId: number
  nodeId: number
}>()

const emit = defineEmits<{
  (e: 'restored'): void
}>()

const visible = defineModel<boolean>({ default: false })

const versions = ref<NodeVersion[]>([])
const loading = ref(false)
const expandedId = ref<number | null>(null)
const restoring = ref(false)

async function loadVersions() {
  loading.value = true
  expandedId.value = null
  try {
    versions.value = await listNodeVersions(props.projectId, props.nodeId)
  } catch {
    ElMessage.error('加载版本历史失败')
  } finally {
    loading.value = false
  }
}

function toggleExpand(ver: NodeVersion) {
  if (expandedId.value === ver.id) {
    expandedId.value = null
  } else {
    expandedId.value = ver.id
  }
}

async function handleRestore(ver: NodeVersion) {
  try {
    await ElMessageBox.confirm(
      `确定恢复到 v${ver.version_number}？当前内容将自动保存为新版本。`,
      '恢复确认',
      { confirmButtonText: '恢复', cancelButtonText: '取消', type: 'warning' },
    )
    restoring.value = true
    await restoreNodeVersion(props.projectId, props.nodeId, ver.id)
    ElMessage.success('已恢复')
    emit('restored')
    visible.value = false
  } catch (e: unknown) {
    if (e !== 'cancel') {
      ElMessage.error('恢复失败')
    }
  } finally {
    restoring.value = false
  }
}

function sourceLabel(source: string): string {
  const map: Record<string, string> = {
    init: '初始',
    ai_apply: 'AI应用',
    switch: '切换',
    manual: '手动',
  }
  return map[source] || source
}

function sourceTagType(source: string): '' | 'success' | 'warning' | 'info' {
  const map: Record<string, '' | 'success' | 'warning' | 'info'> = {
    init: 'info',
    ai_apply: 'warning',
    switch: '',
    manual: 'success',
  }
  return map[source] || 'info'
}

function formatTime(dateStr: string): string {
  const d = new Date(dateStr)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<style scoped>
.version-list {
  max-height: 480px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.version-item {
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  overflow: hidden;
  transition: border-color 0.2s;
}

.version-item--active {
  border-color: #6B7B8D;
}

.version-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.version-header:hover {
  background: #F7F6F3;
}

.version-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.version-number {
  font-size: 13px;
  font-weight: 600;
  color: #6B7B8D;
  min-width: 28px;
}

.version-title {
  font-size: 13px;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 300px;
}

.version-time {
  font-size: 12px;
  color: #9E9E9E;
  flex-shrink: 0;
}

.version-content {
  border-top: 1px solid #E0DFDC;
  padding: 12px 14px;
  background: #FAFAF9;
}

.content-preview {
  font-size: 13px;
  line-height: 1.6;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0 0 10px;
  background: white;
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #ECEAE6;
}

.version-actions {
  text-align: right;
}
</style>