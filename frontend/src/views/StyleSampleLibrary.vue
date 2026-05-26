<template>
  <div class="ssl-page">
    <!-- 顶栏 -->
    <div class="ssl-toolbar">
      <h2>知乎严选风格样本库</h2>
      <div class="ssl-toolbar-actions">
        <el-button type="primary" @click="uploadOpen = true">+ 上传样本</el-button>
        <el-button @click="refresh">刷新</el-button>
        <el-select v-model="genreFilter" placeholder="题材" clearable size="default" style="width: 180px" @change="refresh">
          <el-option v-for="g in genreOptions" :key="g" :label="g" :value="g" />
        </el-select>
      </div>
    </div>

    <!-- 列表 -->
    <el-table :data="samples" v-loading="loading" stripe>
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="author" label="作者" width="100" />
      <el-table-column prop="source" label="来源" width="120" />
      <el-table-column prop="genre" label="题材" width="100" />
      <el-table-column prop="total_chars" label="字数" width="80" />
      <el-table-column label="索引状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.index_status)" effect="plain">
            {{ statusLabel(row.index_status) }}
          </el-tag>
          <el-tooltip v-if="row.index_status === 'failed'" :content="row.index_error || ''">
            <el-icon style="margin-left: 4px"><InfoFilled /></el-icon>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="extracted_at" label="抽取时间" width="180" />
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row.id)">详情</el-button>
          <el-button size="small" @click="onReindex(row)">重抽取</el-button>
          <el-popconfirm title="删除该样本？" @confirm="onDelete(row)">
            <template #reference><el-button size="small" type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadOpen" title="上传风格样本" width="560" @close="resetUpload">
      <el-form :model="uploadForm" label-width="80">
        <el-form-item label="文件" required>
          <el-upload
            :auto-upload="false"
            :on-change="onFileChange"
            :file-list="uploadFiles"
            :limit="1"
            accept=".txt,.md,.markdown,.docx"
          >
            <el-button>选择文件 (txt/md/docx)</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="标题" required><el-input v-model="uploadForm.title" /></el-form-item>
        <el-form-item label="作者"><el-input v-model="uploadForm.author" /></el-form-item>
        <el-form-item label="来源"><el-input v-model="uploadForm.source" placeholder="知乎严选 / 盐选 / 专栏名" /></el-form-item>
        <el-form-item label="题材">
          <el-select v-model="uploadForm.genre" placeholder="可选" clearable>
            <el-option v-for="g in genreOptions" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签"><el-input v-model="uploadForm.tags" placeholder='JSON 数组：["甜文","高糖"]' /></el-form-item>
        <el-form-item label="备注"><el-input v-model="uploadForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadOpen = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!canUpload" @click="onUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailOpen" :title="detailTitle" width="820">
      <div v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="作者">{{ detail.author || '—' }}</el-descriptions-item>
          <el-descriptions-item label="题材">{{ detail.genre || '—' }}</el-descriptions-item>
          <el-descriptions-item label="字数">{{ detail.total_chars }}</el-descriptions-item>
          <el-descriptions-item label="抽取 model">{{ detail.extraction_model || '—' }}</el-descriptions-item>
          <el-descriptions-item label="抽取时间">{{ detail.extracted_at || '—' }}</el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top: 16px">风格指南 — 结构化字段</h4>
        <el-descriptions v-if="detail.style_guide" :column="2" border size="small">
          <el-descriptions-item v-for="(v, k) in flatStructured(detail.style_guide.structured)" :key="k" :label="k">{{ v }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="尚无抽取结果" :image-size="60" />

        <h4 style="margin-top: 16px">风格指南 — 典型节选 (prose_excerpt)</h4>
        <blockquote v-if="detail.style_guide?.prose_excerpt" class="ssl-quote">
          {{ detail.style_guide.prose_excerpt }}
        </blockquote>
        <el-empty v-else description="—" :image-size="40" />

        <h4 style="margin-top: 16px">
          风格指南 — Prompt 片段 (prompt_fragment)
          <el-button v-if="detail.style_guide?.prompt_fragment" size="small" link @click="copyFragment">复制</el-button>
        </h4>
        <pre v-if="detail.style_guide?.prompt_fragment" class="ssl-fragment">{{ detail.style_guide.prompt_fragment }}</pre>
        <el-empty v-else description="—" :image-size="40" />

        <el-collapse style="margin-top: 16px">
          <el-collapse-item title="原文全文" name="content">
            <pre class="ssl-content">{{ detail.content }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  listStyleSamples, getStyleSample, uploadStyleSample,
  deleteStyleSample, reindexStyleSample,
  type StyleSampleSummary, type StyleSampleDetail, type StyleGuideStructured,
} from '@/api/styleSample'

const genreOptions = ['都市言情', '现代言情', '悬疑', '甜宠', '职场', '历史', '其他']

const samples = ref<StyleSampleSummary[]>([])
const loading = ref(false)
const genreFilter = ref<string>('')

const uploadOpen = ref(false)
const uploading = ref(false)
const uploadFiles = ref<{ raw: File }[]>([])
const uploadForm = ref({ title: '', author: '', source: '', genre: '', tags: '', notes: '' })

const detailOpen = ref(false)
const detail = ref<StyleSampleDetail | null>(null)
const detailTitle = computed(() => detail.value ? `详情：${detail.value.title}` : '详情')

let pollTimer: number | null = null

const canUpload = computed(() => uploadForm.value.title && uploadFiles.value.length === 1)

async function refresh() {
  loading.value = true
  try {
    samples.value = await listStyleSamples(genreFilter.value ? { genre: genreFilter.value } : undefined)
  } finally {
    loading.value = false
  }
  schedulePoll()
}

function schedulePoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  const hasInflight = samples.value.some(s => s.index_status === 'pending' || s.index_status === 'indexing')
  if (hasInflight) {
    pollTimer = window.setTimeout(refresh, 5000)
  }
}

function statusTag(s: string) {
  return ({ pending: 'info', indexing: 'primary', ready: 'success', failed: 'danger' } as Record<string, 'info' | 'primary' | 'success' | 'danger'>)[s] || 'info'
}
function statusLabel(s: string) {
  return ({ pending: '待索引', indexing: '索引中', ready: '已就绪', failed: '失败' } as Record<string, string>)[s] || s
}

function onFileChange(file: { raw: File }) {
  uploadFiles.value = [file]
}

async function onUpload() {
  if (!canUpload.value) return
  uploading.value = true
  try {
    await uploadStyleSample(uploadFiles.value[0].raw, uploadForm.value)
    ElMessage.success('已上传，正在后台索引')
    uploadOpen.value = false
    resetUpload()
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

function resetUpload() {
  uploadForm.value = { title: '', author: '', source: '', genre: '', tags: '', notes: '' }
  uploadFiles.value = []
}

async function openDetail(id: number) {
  detail.value = await getStyleSample(id)
  detailOpen.value = true
}

async function onDelete(row: StyleSampleSummary) {
  await deleteStyleSample(row.id)
  ElMessage.success('已删除')
  await refresh()
}

async function onReindex(row: StyleSampleSummary) {
  await reindexStyleSample(row.id)
  ElMessage.success('已触发重抽取')
  await refresh()
}

function flatStructured(s: StyleGuideStructured): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(s)) {
    if (v == null) continue
    out[k] = Array.isArray(v) ? v.join('、') : String(v)
  }
  return out
}

function copyFragment() {
  if (!detail.value?.style_guide) return
  navigator.clipboard.writeText(detail.value.style_guide.prompt_fragment)
  ElMessage.success('已复制')
}

onMounted(refresh)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>

<style scoped>
.ssl-page { padding: 16px; }
.ssl-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.ssl-toolbar-actions { display: flex; gap: 8px; align-items: center; }
.ssl-quote { background: var(--el-fill-color-light); padding: 12px; border-left: 3px solid var(--el-color-primary); margin: 8px 0; white-space: pre-wrap; }
.ssl-fragment { background: var(--el-fill-color-light); padding: 12px; white-space: pre-wrap; font-family: inherit; }
.ssl-content { max-height: 400px; overflow: auto; white-space: pre-wrap; font-family: inherit; }
</style>
