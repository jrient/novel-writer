<template>
  <div class="rubric-score-page">
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.back()">返回</el-button>
          <h1 class="page-title">剧本评分</h1>
        </div>
        <div class="header-right">
          <el-tag v-if="result" type="info" size="small">handbook {{ result.handbook_version }} · {{ result.model }}</el-tag>
        </div>
      </div>
    </header>

    <main class="page-main">
      <!-- 输入区 -->
      <el-card class="section-card input-card" shadow="never">
        <template #header>
          <div class="card-header">
            <span class="header-title">飞书剧本链接</span>
          </div>
        </template>
        <div class="input-block">
          <el-input
            v-model="docUrl"
            placeholder="粘贴飞书 docx 链接，例如 https://xxx.feishu.cn/docx/PahPd5hkZoPkGsx83apcWXQWnDd"
            clearable
            :disabled="loading"
            @keyup.enter="onScore"
          >
            <template #prefix>
              <el-icon><Link /></el-icon>
            </template>
          </el-input>
          <div class="input-actions">
            <el-checkbox v-model="forceRefresh" :disabled="loading">
              强制刷新（跳过本地缓存）
            </el-checkbox>
            <el-button
              type="primary"
              :loading="loading"
              :disabled="!docUrl.trim()"
              @click="onScore"
            >
              {{ loading ? '正在评分...' : '开始评分' }}
            </el-button>
          </div>
          <div v-if="lastError" class="error-text">{{ lastError }}</div>
          <div v-if="loading" class="loading-hint">
            <el-icon class="is-loading"><Loading /></el-icon>
            正在拉取正文 + 调用 LLM 评分，通常需要 30-90 秒，请耐心等待
          </div>
        </div>
      </el-card>

      <!-- 结果区 -->
      <template v-if="result">
        <!-- 总览 -->
        <el-card class="section-card verdict-card" shadow="never">
          <div class="verdict-row">
            <div class="verdict-title-block">
              <div class="verdict-meta">{{ result.docx_token }} · {{ result.text_length.toLocaleString() }} 字</div>
              <h2 class="verdict-title">{{ result.title }}</h2>
            </div>
            <div class="verdict-score-block">
              <div class="verdict-score" :class="`score-${scoreTier(result.predicted_score)}`">
                {{ result.predicted_score }}
              </div>
              <el-tag :type="statusTagType(result.predicted_status)" size="large" effect="dark">
                {{ result.predicted_status }}
              </el-tag>
            </div>
          </div>
        </el-card>

        <!-- 维度分 -->
        <el-card class="section-card dim-card" shadow="never">
          <template #header>
            <div class="card-header"><span class="header-title">维度评分</span></div>
          </template>
          <div class="dim-list">
            <div v-for="(label, key) in DIMENSION_LABELS" :key="key" class="dim-row">
              <span class="dim-label">{{ label }}</span>
              <div class="dim-bar-wrap">
                <el-progress
                  :percentage="((result.dimension_scores[key] ?? 0) / 10) * 100"
                  :stroke-width="14"
                  :color="dimColor(result.dimension_scores[key] ?? 0)"
                  :show-text="false"
                />
              </div>
              <span class="dim-score">{{ result.dimension_scores[key] ?? '-' }}/10</span>
            </div>
          </div>
        </el-card>

        <!-- 红/绿旗 -->
        <el-card v-if="result.red_flags_hit.length || result.green_flags_hit.length" class="section-card flag-card" shadow="never">
          <template #header>
            <div class="card-header"><span class="header-title">红绿旗命中</span></div>
          </template>
          <div class="flag-block" v-if="result.red_flags_hit.length">
            <div class="flag-title flag-title-red">
              <el-icon><WarningFilled /></el-icon>
              <span>红旗（{{ result.red_flags_hit.length }}）</span>
            </div>
            <ul class="flag-list">
              <li v-for="(f, i) in result.red_flags_hit" :key="`r-${i}`">{{ f }}</li>
            </ul>
          </div>
          <div class="flag-block" v-if="result.green_flags_hit.length">
            <div class="flag-title flag-title-green">
              <el-icon><CircleCheckFilled /></el-icon>
              <span>绿旗（{{ result.green_flags_hit.length }}）</span>
            </div>
            <ul class="flag-list">
              <li v-for="(f, i) in result.green_flags_hit" :key="`g-${i}`">{{ f }}</li>
            </ul>
          </div>
        </el-card>

        <!-- 修改建议 -->
        <el-card v-if="result.comments.length" class="section-card comment-card" shadow="never">
          <template #header>
            <div class="card-header"><span class="header-title">修改建议</span></div>
          </template>
          <ol class="comment-list">
            <li v-for="(c, i) in result.comments" :key="`c-${i}`">{{ c }}</li>
          </ol>
        </el-card>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  ArrowLeft,
  Link,
  Loading,
  WarningFilled,
  CircleCheckFilled,
} from '@element-plus/icons-vue'
import { rubricApi, type ScoreDocxResponse } from '@/api/rubric'

const router = useRouter()

const docUrl = ref('')
const forceRefresh = ref(true)
const loading = ref(false)
const result = ref<ScoreDocxResponse | null>(null)
const lastError = ref('')

const DIMENSION_LABELS: Record<string, string> = {
  premise_innovation: '题材与设定创新度',
  opening_hook: '开局与钩子',
  character_depth: '人设立体度',
  pacing_conflict: '节奏与冲突密度',
  writing_dialogue: '文笔与台词',
  payoff_satisfaction: '爽点兑现',
  benchmark_differentiation: '对标与差异化',
}

function scoreTier(s: number): 'high' | 'mid' | 'low' {
  if (s >= 80) return 'high'
  if (s >= 70) return 'mid'
  return 'low'
}

function statusTagType(status: string): 'success' | 'warning' | 'danger' | 'info' {
  if (status === '签') return 'success'
  if (status === '改') return 'warning'
  if (status === '拒') return 'danger'
  return 'info'
}

function dimColor(score: number): string {
  if (score >= 8) return '#67c23a'
  if (score >= 6) return '#e6a23c'
  if (score >= 4) return '#f56c6c'
  return '#c0392b'
}

async function onScore() {
  const url = docUrl.value.trim()
  if (!url) return
  loading.value = true
  lastError.value = ''
  result.value = null
  try {
    result.value = await rubricApi.scoreDocx(url, forceRefresh.value)
    ElMessage.success(`评分完成：${result.value.predicted_score} / ${result.value.predicted_status}`)
  } catch (e: any) {
    const msg = e?.response?.data?.detail || e?.message || '评分失败'
    lastError.value = msg
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.rubric-score-page {
  min-height: 100vh;
  background: #f5f7fa;
  padding-bottom: 48px;
}

.page-header {
  background: #fff;
  border-bottom: 1px solid #ebeef5;
  position: sticky;
  top: 0;
  z-index: 10;
}
.header-content {
  max-width: 960px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.page-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #303133;
}

.page-main {
  max-width: 960px;
  margin: 0 auto;
  padding: 20px 24px 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card :deep(.el-card__header) {
  padding: 12px 18px;
  border-bottom: 1px solid #f0f2f5;
}
.section-card :deep(.el-card__body) {
  padding: 18px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-title {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

/* Input */
.input-block {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.error-text {
  color: #f56c6c;
  font-size: 13px;
  background: #fef0f0;
  border-left: 3px solid #f56c6c;
  padding: 8px 12px;
  border-radius: 4px;
  white-space: pre-wrap;
}
.loading-hint {
  color: #909399;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Verdict */
.verdict-card :deep(.el-card__body) {
  padding: 24px 24px;
}
.verdict-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  flex-wrap: wrap;
}
.verdict-title-block {
  flex: 1;
  min-width: 0;
}
.verdict-meta {
  font-size: 12px;
  color: #909399;
  margin-bottom: 6px;
  font-family: monospace;
}
.verdict-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
  line-height: 1.4;
  word-break: break-word;
}
.verdict-score-block {
  display: flex;
  align-items: center;
  gap: 14px;
}
.verdict-score {
  font-size: 48px;
  font-weight: 700;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.verdict-score.score-high { color: #67c23a; }
.verdict-score.score-mid  { color: #e6a23c; }
.verdict-score.score-low  { color: #f56c6c; }

/* Dimension */
.dim-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dim-row {
  display: grid;
  grid-template-columns: 140px 1fr 60px;
  align-items: center;
  gap: 12px;
}
.dim-label {
  font-size: 13px;
  color: #606266;
}
.dim-bar-wrap {
  width: 100%;
}
.dim-score {
  text-align: right;
  font-family: monospace;
  font-size: 13px;
  color: #303133;
}

/* Flags */
.flag-block {
  margin-bottom: 14px;
}
.flag-block:last-child {
  margin-bottom: 0;
}
.flag-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 8px;
}
.flag-title-red { color: #f56c6c; }
.flag-title-green { color: #67c23a; }
.flag-list {
  margin: 0;
  padding-left: 22px;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}

/* Comments */
.comment-list {
  margin: 0;
  padding-left: 22px;
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
}
.comment-list li {
  margin-bottom: 8px;
}
.comment-list li:last-child {
  margin-bottom: 0;
}

@media (max-width: 640px) {
  .verdict-row { flex-direction: column; align-items: flex-start; }
  .dim-row { grid-template-columns: 110px 1fr 50px; gap: 8px; }
  .dim-label { font-size: 12px; }
}
</style>
