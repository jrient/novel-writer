<template>
  <div class="adaptation-wb">
    <div class="topbar">
      <div class="left">
        <h3>{{ project?.title || '...' }}</h3>
        <el-select v-if="versions.length" v-model="currentVid" size="small" style="width: 140px">
          <el-option v-for="v in versions" :key="v.id" :label="`v${v.version_no} (${v.status})`" :value="v.id" />
        </el-select>
      </div>
      <div class="right">
        <el-button :loading="running" @click="onFullRun">全场重跑</el-button>
        <el-button @click="onExport('txt')">导出 .txt</el-button>
        <el-button @click="onExport('docx')">导出 .docx</el-button>
      </div>
    </div>

    <div v-if="progress.total" class="progress">
      <el-progress :percentage="Math.round(progress.done / progress.total * 100)" :status="running ? '' : 'success'" />
      <span>{{ progress.done }} / {{ progress.total }} 场完成（失败 {{ progress.failed }}）</span>
    </div>

    <el-empty
      v-if="!versions.length"
      :description="`已切 ${project?.scene_boundaries?.length ?? 0} 场 · ${project?.mappings?.length ?? 0} 条映射`"
    >
      <template #default>
        <div class="empty-hint">
          <p>还没有生成改编版本。点击下方按钮开始首次改写：</p>
          <el-button type="primary" :loading="running" @click="onFullRun">
            开始改写（全场）
          </el-button>
          <p class="empty-sub">改写完成前可关闭页面，再次进入会自动续显进度。</p>
        </div>
      </template>
    </el-empty>

    <el-table v-else :data="scenes" size="small" @row-click="openDrawer">
      <el-table-column label="#" width="60" prop="scene_index" />
      <el-table-column label="状态" width="100">
        <template #default="{row}">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="场标题" prop="scene_title" />
      <el-table-column label="行数偏差" width="100">
        <template #default="{row}">
          <span v-if="row.line_count_delta_pct != null" :class="deltaClass(row)">
            {{ (row.line_count_delta_pct * 100).toFixed(0) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column label="" width="100">
        <template #default="{row}">
          <el-button
            link size="small"
            :loading="rerunningIdx === row.scene_index"
            :disabled="rerunningIdx !== null && rerunningIdx !== row.scene_index"
            @click.stop="quickRerun(row)"
          >重跑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="drawerVisible" :title="`场 ${((active?.scene_index ?? 0) + 1)}`" size="80%" direction="btt">
      <el-tabs v-if="active" v-model="tab">
        <el-tab-pane label="原文" name="orig">
          <pre class="scene-text">{{ active.original_scene_text }}</pre>
        </el-tab-pane>
        <el-tab-pane label="改编后" name="new">
          <el-input v-model="editing" type="textarea" :rows="20" />
        </el-tab-pane>
        <el-tab-pane label="Diff" name="diff">
          <pre class="scene-text" v-html="diffHtml" />
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <div class="drawer-foot">
          <el-input v-model="extraPrompt" placeholder="（可选）本次重跑的额外提示词" style="flex: 1; margin-right: 8px" />
          <el-button @click="onRerun" :loading="rerunning">单场重跑</el-button>
          <el-button type="primary" @click="onSaveManual">保存手改</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adaptationApi, type AdaptationProject, type AdaptationVersion, type SceneResult } from '@/api/adaptation'

const route = useRoute()
const projectId = Number(route.params.id)

const project = ref<AdaptationProject | null>(null)
const versions = ref<AdaptationVersion[]>([])
const currentVid = ref<number | null>(null)
const scenes = ref<SceneResult[]>([])
const running = ref(false)
const drawerVisible = ref(false)
const active = ref<SceneResult | null>(null)
const editing = ref('')
const extraPrompt = ref('')
const rerunning = ref(false)
const rerunningIdx = ref<number | null>(null)
const tab = ref('new')
let es: EventSource | null = null

const progress = computed(() => ({
  total: scenes.value.length,
  done: scenes.value.filter(s => s.status === 'done' || s.status === 'manual_edited').length,
  failed: scenes.value.filter(s => s.status === 'failed').length,
}))

function lineSim(a: string, b: string): number {
  if (a === b) return 1
  if (!a || !b) return 0
  const counts = new Map<string, number>()
  for (const ch of a) counts.set(ch, (counts.get(ch) || 0) + 1)
  let inter = 0
  for (const ch of b) {
    const n = counts.get(ch) || 0
    if (n > 0) { inter++; counts.set(ch, n - 1) }
  }
  return inter / Math.max(a.length, b.length)
}

// m*n 超过该阈值时回退到朴素逐行 diff，避免在大场（几百行 × 几百行）上卡顿
const LCS_CELL_LIMIT = 10000

function naiveDiff(orig: string[], cur: string[]): string {
  const max = Math.max(orig.length, cur.length)
  let html = ''
  for (let i = 0; i < max; i++) {
    const o = orig[i] ?? ''
    const c = cur[i] ?? ''
    if (o === c) html += `  ${escape(o)}\n`
    else {
      if (o) html += `<span style="color:#f56c6c">- ${escape(o)}</span>\n`
      if (c) html += `<span style="color:#67c23a">+ ${escape(c)}</span>\n`
    }
  }
  return html
}

const diffHtml = computed(() => {
  if (!active.value) return ''
  const orig = (active.value.original_scene_text || '').split('\n')
  const cur = (active.value.rewritten_scene_text || '').split('\n')
  const m = orig.length, n = cur.length
  // 大场回退到朴素 diff，避免 O(m·n·L) 卡死页面
  if (m * n > LCS_CELL_LIMIT) return naiveDiff(orig, cur)

  // 字符重合度 ≥0.30 视作"同一行的改写"，做 LCS 对齐
  const SIM = 0.30
  // 预计算 sim 矩阵：每对 (i,j) 只跑一次 lineSim，DP 与 traceback 共享
  const sim: boolean[][] = Array.from({ length: m }, () => new Array(n).fill(false))
  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      sim[i][j] = lineSim(orig[i], cur[j]) >= SIM
    }
  }
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] = sim[i][j]
        ? dp[i + 1][j + 1] + 1
        : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  let html = ''
  let i = 0, j = 0
  while (i < m && j < n) {
    if (sim[i][j]) {
      if (orig[i] === cur[j]) {
        html += `  ${escape(orig[i])}\n`
      } else {
        html += `<span style="color:#f56c6c">- ${escape(orig[i])}</span>\n`
        html += `<span style="color:#67c23a">+ ${escape(cur[j])}</span>\n`
      }
      i++; j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      html += `<span style="color:#f56c6c">- ${escape(orig[i])}</span>\n`; i++
    } else {
      html += `<span style="color:#67c23a">+ ${escape(cur[j])}</span>\n`; j++
    }
  }
  while (i < m) html += `<span style="color:#f56c6c">- ${escape(orig[i++])}</span>\n`
  while (j < n) html += `<span style="color:#67c23a">+ ${escape(cur[j++])}</span>\n`
  return html
})

function escape(s: string) {
  return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]!))
}

function statusType(s: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  if (s === 'done') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  if (s === 'manual_edited') return 'info'
  return ''
}

function deltaClass(row: SceneResult) {
  const pct = Math.abs((row.line_count_delta_pct ?? 0) * 100)
  if (!project.value) return ''
  const lim = project.value.intensity === 1 ? 0 : project.value.intensity === 2 ? 5 : 20
  return pct > lim ? 'delta-warn' : ''
}

async function loadProject() {
  const r = await adaptationApi.get(projectId) as any
  project.value = r
  versions.value = r.versions
  if (!currentVid.value && versions.value.length) {
    currentVid.value = Math.max(...versions.value.map((v: any) => v.id))
  }
}

async function loadVersion() {
  if (!currentVid.value) { scenes.value = []; return }
  const r = await adaptationApi.getRun(currentVid.value) as any
  scenes.value = r.scene_results
  running.value = r.status === 'running'
  if (running.value) connectSSE()
}

watch(currentVid, loadVersion)

async function connectSSE() {
  if (!currentVid.value) return
  closeSSE()
  let ticket: string
  try {
    const r = await adaptationApi.getStreamTicket(currentVid.value) as any
    ticket = r.ticket
  } catch (e) {
    // 拿不到 ticket（鉴权失败等）就直接放弃订阅，loadVersion 会兜底轮询
    return
  }
  es = new EventSource(adaptationApi.streamUrl(currentVid.value, ticket))
  es.onmessage = ev => {
    if (!ev.data) return
    let payload: any
    try { payload = JSON.parse(ev.data) } catch { return }
    if (payload.event === 'scene_done' || payload.event === 'scene_running') {
      const idx = scenes.value.findIndex(s => s.scene_index === payload.scene_index)
      if (idx >= 0) {
        if (payload.event === 'scene_running') scenes.value[idx].status = 'running'
        else {
          scenes.value[idx].status = payload.status
          scenes.value[idx].rewritten_scene_text = payload.rewritten
          scenes.value[idx].error = payload.error
          scenes.value[idx].line_count_delta_pct = payload.line_count_delta_pct
        }
      }
    }
    if (payload.event === 'version_done' || payload.event === 'version_failed') {
      running.value = false
      closeSSE()
      loadVersion()
      loadProject()
    }
  }
  es.onerror = () => { closeSSE(); setTimeout(() => running.value && loadVersion(), 1000) }
}

function closeSSE() { if (es) { es.close(); es = null } }

async function onFullRun() {
  if (!project.value) return
  running.value = true
  const r = await adaptationApi.createRun(project.value.id, extraPrompt.value || undefined) as any
  currentVid.value = r.id
  await loadProject()
  await loadVersion()
}

function openDrawer(row: SceneResult) {
  active.value = row
  editing.value = row.rewritten_scene_text || ''
  extraPrompt.value = ''
  tab.value = 'new'
  drawerVisible.value = true
}

function _humanErr(e: any): string {
  const detail = e?.response?.data?.detail
  if (typeof detail === 'string') return detail
  return e?.message || '请求失败'
}

async function _rerunOne(target: SceneResult, prompt?: string) {
  if (!currentVid.value) return
  rerunningIdx.value = target.scene_index
  ElMessage.info(`正在改写场 ${target.scene_index + 1}，请稍候…`)
  try {
    const r = await adaptationApi.rerunScene(currentVid.value, target.scene_index, prompt) as any
    const idx = scenes.value.findIndex(s => s.scene_index === r.scene_index)
    if (idx >= 0) scenes.value[idx] = r
    if (active.value?.scene_index === r.scene_index) {
      active.value = r
      editing.value = r.rewritten_scene_text || ''
    }
    if (r.status === 'failed') {
      ElMessage.error(`场 ${r.scene_index + 1} 改写失败：${r.error || '未知错误'}`)
    } else {
      ElMessage.success(`场 ${r.scene_index + 1} 已重跑完成`)
    }
  } catch (e: any) {
    ElMessage.error(`重跑失败：${_humanErr(e)}`)
  } finally {
    rerunningIdx.value = null
  }
}

async function onRerun() {
  if (!active.value) return
  rerunning.value = true
  try {
    await _rerunOne(active.value, extraPrompt.value || undefined)
  } finally { rerunning.value = false }
}

async function quickRerun(row: SceneResult) {
  await _rerunOne(row)
}

async function onSaveManual() {
  if (!active.value || !currentVid.value) return
  const r = await adaptationApi.patchScene(currentVid.value, active.value.scene_index, editing.value) as any
  active.value = r
  const idx = scenes.value.findIndex(s => s.scene_index === r.scene_index)
  if (idx >= 0) scenes.value[idx] = r
  ElMessage.success('手改已保存')
}

function onExport(fmt: 'txt' | 'docx') {
  if (!currentVid.value) return
  window.open(adaptationApi.exportUrl(currentVid.value, fmt), '_blank')
}

onMounted(async () => { await loadProject(); await loadVersion() })
onUnmounted(closeSSE)
</script>

<style scoped>
.adaptation-wb { padding: 16px 24px; max-width: 1200px; margin: 0 auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.topbar .left { display: flex; align-items: center; gap: 12px; }
.progress { margin: 8px 0 16px; display: flex; align-items: center; gap: 12px; }
.scene-text { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.6; }
.delta-warn { color: #e6a23c; font-weight: 600; }
.drawer-foot { display: flex; align-items: center; }
.empty-hint { text-align: center; }
.empty-hint p { margin: 8px 0; color: #606266; }
.empty-sub { font-size: 12px; color: #909399; }
</style>
