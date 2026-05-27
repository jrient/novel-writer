<template>
  <div style="padding: 24px">
    <!-- 项目信息头 -->
    <div v-if="project" style="margin-bottom: 16px">
      <div style="display: flex; justify-content: space-between; align-items: flex-start">
        <div>
          <h2 style="margin: 0 0 4px">{{ project.title }}</h2>
          <el-text type="info">
            来源：{{ project.script_project_title || `剧本 #${project.script_project_id}` }}
            ｜ 梗概：{{ project.premise }}
          </el-text>
        </div>
        <div style="display: flex; gap: 8px">
          <el-button
            v-if="project.status === 'done' || project.status === 'partial'"
            @click="exportTxt"
          >导出 TXT</el-button>
          <el-button @click="$router.push('/prose')">返回列表</el-button>
        </div>
      </div>

      <!-- 进度 -->
      <div style="margin-top: 12px">
        <el-tag :type="statusTagType(project.status)" style="margin-right: 8px">
          {{ statusLabel(project.status) }}
        </el-tag>
        <el-progress
          v-if="project.status === 'generating'"
          :percentage="progressPct"
          style="display: inline-flex; width: 300px; vertical-align: middle"
        />
        <el-text v-else type="info">
          {{ project.done_scenes }}/{{ project.total_scenes }} 场完成
          <span v-if="project.failed_scenes > 0" style="color: #f56c6c">
            ，{{ project.failed_scenes }} 场失败
          </span>
        </el-text>
      </div>

      <!-- 风格快照折叠 -->
      <el-collapse style="margin-top: 12px" v-if="styleSnapshot.length">
        <el-collapse-item title="风格样本快照" name="snapshot">
          <div v-for="s in styleSnapshot" :key="s.sample_id" style="margin-bottom: 12px">
            <strong>{{ s.title }}</strong>
            <div style="background: #f5f5f5; padding: 8px; border-radius: 4px; margin-top: 4px; font-size: 13px">
              {{ s.prompt_fragment }}
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <el-skeleton v-if="!project" :rows="5" animated />

    <!-- 场次列表 -->
    <el-collapse v-if="project" v-model="openScenes" accordion style="margin-top: 8px">
      <el-collapse-item
        v-for="scene in scenes"
        :key="scene.id"
        :name="scene.scene_index"
      >
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px">
            <span>{{ scene.scene_title || `场 ${scene.scene_index + 1}` }}</span>
            <el-tag :type="sceneTagType(scene.status)" size="small">
              {{ sceneLabel(scene.status) }}
            </el-tag>
          </div>
        </template>

        <div v-if="scene.status === 'done' && scene.prose_text"
             style="white-space: pre-wrap; line-height: 1.8; padding: 8px">
          {{ scene.prose_text }}
        </div>
        <div v-else-if="scene.status === 'failed'"
             style="color: #f56c6c; padding: 8px">
          生成失败：{{ scene.error || '未知错误' }}
        </div>
        <div v-else style="color: #909399; padding: 8px">
          {{ scene.status === 'running' ? '生成中…' : '等待中' }}
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { ProseProjectDetail, ProseSceneOut } from '@/api/prose'
import { proseApi } from '@/api/prose'

const route = useRoute()
const projectId = Number(route.params.id)

const project = ref<ProseProjectDetail | null>(null)
const scenes = ref<ProseSceneOut[]>([])
const openScenes = ref<number[]>([])
let eventSource: EventSource | null = null

const styleSnapshot = computed(() => {
  if (!project.value?.style_snapshot) return []
  try {
    return JSON.parse(project.value.style_snapshot)
  } catch {
    return []
  }
})

const progressPct = computed(() => {
  if (!project.value || !project.value.total_scenes) return 0
  return Math.round(
    ((project.value.done_scenes + project.value.failed_scenes) / project.value.total_scenes) * 100
  )
})

function statusTagType(status: string) {
  const m: Record<string, string> = { pending: 'info', generating: 'primary', done: 'success', partial: 'warning', failed: 'danger' }
  return m[status] ?? 'info'
}

function statusLabel(status: string) {
  const m: Record<string, string> = { pending: '等待中', generating: '生成中', done: '完成', partial: '部分完成', failed: '失败' }
  return m[status] ?? status
}

function sceneTagType(status: string) {
  const m: Record<string, string> = { pending: 'info', running: 'primary', done: 'success', failed: 'danger' }
  return m[status] ?? 'info'
}

function sceneLabel(status: string) {
  const m: Record<string, string> = { pending: '等待', running: '生成中', done: '完成', failed: '失败' }
  return m[status] ?? status
}

async function loadDetail() {
  try {
    const res = await proseApi.get(projectId)
    project.value = res
    scenes.value = res.scenes
  } catch {
    ElMessage.error('加载失败')
  }
}

async function startSSE() {
  try {
    const ticketRes = await proseApi.getStreamTicket(projectId)
    const url = proseApi.getStreamUrl(projectId, (ticketRes as { ticket: string }).ticket)
    eventSource = new EventSource(url)

    eventSource.onmessage = (e) => {
      const payload = JSON.parse(e.data)
      if (payload.event === 'scene_done') {
        const idx = scenes.value.findIndex(s => s.scene_index === payload.scene_index)
        if (idx >= 0) {
          scenes.value[idx] = {
            ...scenes.value[idx],
            status: payload.status,
            prose_text: payload.prose_text ?? null,
          }
        }
        if (project.value) {
          if (payload.status === 'done') project.value.done_scenes++
          else if (payload.status === 'failed') project.value.failed_scenes++
        }
      } else if (payload.event === 'project_done' || payload.event === 'project_failed') {
        if (project.value) project.value.status = payload.event === 'project_done' ? 'done' : payload.status
        eventSource?.close()
        eventSource = null
        loadDetail()
      }
    }
    eventSource.onerror = () => {
      eventSource?.close()
      eventSource = null
    }
  } catch {
    // SSE 失败降级，不影响页面显示
  }
}

function exportTxt() {
  const lines = scenes.value
    .filter(s => s.prose_text)
    .map(s => `## ${s.scene_title || `场 ${s.scene_index + 1}`}\n\n${s.prose_text}`)
    .join('\n\n---\n\n')
  const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${project.value?.title ?? '散文'}.txt`
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  await loadDetail()
  if (project.value?.status === 'generating' || project.value?.status === 'pending') {
    await startSSE()
  }
})

onBeforeUnmount(() => {
  eventSource?.close()
})
</script>
