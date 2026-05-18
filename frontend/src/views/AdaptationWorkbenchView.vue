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
        <el-button
          type="primary" plain
          :loading="scoring"
          :disabled="!currentVid || running"
          @click="onScore"
        >评分</el-button>
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

    <el-dialog
      v-model="scoreDialog"
      title="剧本评分"
      width="780px"
      :close-on-click-modal="false"
    >
      <div v-if="scoreResult" class="score-result">
        <div class="score-head">
          <div class="score-num">
            <span class="score-val">{{ scoreResult.predicted_score }}</span>
            <span class="score-sep">/ 100</span>
          </div>
          <div class="score-meta">
            <el-tag :type="statusTagType(scoreResult.predicted_status)" effect="dark">
              {{ scoreResult.predicted_status }}
            </el-tag>
            <span class="score-hand">handbook {{ scoreResult.handbook_version }} · {{ scoreResult.model }}</span>
          </div>
        </div>

        <h4 class="score-section-title">维度分</h4>
        <div class="score-dims">
          <div v-for="(val, key) in scoreResult.dimension_scores" :key="key" class="dim-row">
            <span class="dim-name">{{ dimLabel(String(key)) }}</span>
            <el-progress
              :percentage="Math.min(100, (Number(val) || 0) * 10)"
              :stroke-width="10"
              :show-text="false"
              :color="dimColor(Number(val))"
              style="flex: 1; margin: 0 12px"
            />
            <span class="dim-val">{{ val }}</span>
          </div>
        </div>

        <template v-if="scoreResult.red_flags_hit && scoreResult.red_flags_hit.length">
          <h4 class="score-section-title">命中红线</h4>
          <ul class="score-flags red">
            <li v-for="(f, i) in scoreResult.red_flags_hit" :key="i">{{ f }}</li>
          </ul>
        </template>

        <template v-if="scoreResult.green_flags_hit && scoreResult.green_flags_hit.length">
          <h4 class="score-section-title">亮点</h4>
          <ul class="score-flags green">
            <li v-for="(f, i) in scoreResult.green_flags_hit" :key="i">{{ f }}</li>
          </ul>
        </template>

        <template v-if="scoreResult.comments && scoreResult.comments.length">
          <h4 class="score-section-title">修改建议</h4>
          <ol class="score-comments">
            <li v-for="(c, i) in scoreResult.comments" :key="i">{{ c }}</li>
          </ol>
        </template>
      </div>
      <div v-else-if="scoring" class="score-loading">
        <el-icon class="is-loading"><Loading /></el-icon>
        <span>正在调用 handbook 评分，通常需要 30~60 秒…</span>
      </div>
      <template #footer>
        <el-button @click="scoreDialog = false">关闭</el-button>
        <el-button type="primary" :loading="scoring" @click="onScore">重新评分</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { adaptationApi, type AdaptationProject, type AdaptationVersion, type SceneResult } from '@/api/adaptation'
import type { ScoreDocxResponse } from '@/api/rubric'

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
const scoring = ref(false)
const scoreDialog = ref(false)
const scoreResult = ref<ScoreDocxResponse | null>(null)
let es: EventSource | null = null

const _DIM_LABELS: Record<string, string> = {
  premise_innovation: '题材创新',
  opening_hook: '开局钩子',
  character_depth: '人设立体',
  pacing_conflict: '节奏冲突',
  writing_dialogue: '文笔对白',
  payoff_satisfaction: '爽点兑现',
  benchmark_differentiation: '对标差异',
}
function dimLabel(key: string): string {
  return _DIM_LABELS[key] || key
}
function dimColor(val: number): string {
  if (val >= 8) return '#67c23a'
  if (val >= 6) return '#e6a23c'
  return '#f56c6c'
}
function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === '签') return 'success'
  if (status === '改') return 'warning'
  if (status === '拒') return 'danger'
  return 'info'
}

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

async function onScore() {
  if (!currentVid.value || scoring.value) return
  scoring.value = true
  scoreDialog.value = true
  scoreResult.value = null
  try {
    const r = await adaptationApi.scoreRun(currentVid.value)
    scoreResult.value = r as unknown as ScoreDocxResponse
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || e?.message || '评分失败')
    scoreDialog.value = false
  } finally {
    scoring.value = false
  }
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

.score-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 8px;
}
.score-num { display: flex; align-items: baseline; }
.score-val { font-size: 44px; font-weight: 600; color: #303133; line-height: 1; }
.score-sep { margin-left: 6px; font-size: 14px; color: #909399; }
.score-meta { display: flex; flex-direction: column; gap: 6px; }
.score-hand { font-size: 12px; color: #909399; }

.score-section-title {
  margin: 20px 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  border-left: 3px solid #409eff;
  padding-left: 8px;
}
.score-dims { display: flex; flex-direction: column; gap: 8px; }
.dim-row { display: flex; align-items: center; font-size: 13px; }
.dim-name { width: 88px; color: #606266; }
.dim-val { width: 32px; text-align: right; color: #303133; font-weight: 600; }

.score-flags { margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.7; }
.score-flags.red li { color: #f56c6c; }
.score-flags.green li { color: #67c23a; }
.score-comments { margin: 0; padding-left: 20px; font-size: 13px; line-height: 1.7; color: #606266; }

.score-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 36px 12px;
  color: #909399;
  justify-content: center;
}
</style>
