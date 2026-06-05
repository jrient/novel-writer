<template>
  <div class="reference-library-page">
    <header class="page-header">
      <div class="header-left">
        <el-button text :icon="ArrowLeft" @click="$router.back()">返回</el-button>
        <h2 class="page-title">原作知识图谱库</h2>
        <el-text type="info" size="small">管理原作设定与知识图谱</el-text>
      </div>
      <div class="header-right">
        <el-upload
          action="/api/v1/references"
          :show-file-list="false"
          :before-upload="handleBeforeUpload"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :headers="uploadHeaders"
          accept=".txt,.epub"
        >
          <el-button type="primary" :icon="Upload">上传小说</el-button>
        </el-upload>
      </div>
    </header>

    <main class="page-main">
      <el-empty v-if="!loading && references.length === 0"
                description="尚未上传原作，点击上方按钮上传小说文本">
        <el-text type="info" size="small" style="display:block;margin-top:8px">
          支持 .txt / .epub 格式
        </el-text>
      </el-empty>

      <div v-else class="reference-grid">
        <el-card
          v-for="ref in references"
          :key="ref.id"
          class="reference-card"
          shadow="hover"
          @click="goToCanon(ref.id)"
        >
          <div class="ref-head">
            <h4 class="ref-title">{{ ref.title || '未命名' }}</h4>
            <el-tag v-if="ref.reference_type" size="small" type="info" effect="plain">
              {{ ref.reference_type }}
            </el-tag>
          </div>
          <p class="ref-meta">
            <span v-if="ref.author">作者：{{ ref.author }}</span>
            <span v-if="ref.genre">· {{ ref.genre }}</span>
          </p>
          <div class="ref-stats">
            <span>{{ (ref.total_chars || 0).toLocaleString() }} 字</span>
            <span v-if="ref.chapter_count > 0">· {{ ref.chapter_count }} 章</span>
          </div>
          <div class="ref-actions">
            <el-button text size="small" type="primary"
                       @click.stop="goToCanon(ref.id)">
              <el-icon><View /></el-icon> 查看设定与图谱
            </el-button>
            <el-button text size="small" type="danger"
                       @click.stop="handleDelete(ref)">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
          </div>
        </el-card>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Upload, View, Delete } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { getReferences, deleteReference } from '@/api/reference'
import type { ReferenceNovel } from '@/api/reference'
import type { UploadRawFile } from 'element-plus'

const router = useRouter()
const userStore = useUserStore()
const references = ref<ReferenceNovel[]>([])
const loading = ref(false)

const uploadHeaders = ref<Record<string, string>>({})

onMounted(async () => {
  loading.value = true
  try {
    references.value = await getReferences()
  } catch {
    ElMessage.error('加载原作列表失败')
  } finally {
    loading.value = false
  }
})

function handleBeforeUpload(file: UploadRawFile) {
  const token = localStorage.getItem('token') || ''
  uploadHeaders.value = { Authorization: token ? `Bearer ${token}` : '' }
  return true
}
function handleUploadSuccess() {
  ElMessage.success('上传成功')
  getReferences().then(r => { references.value = r })
  return false
}
function handleUploadError() {
  ElMessage.error('上传失败')
}

function goToCanon(id: number) {
  router.push(`/references/${id}/canon`)
}

async function handleDelete(ref: ReferenceNovel) {
  try {
    await ElMessageBox.confirm(`确认删除「${ref.title}」？此操作不可撤销。`, '删除确认', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteReference(ref.id)
    ElMessage.success('已删除')
    references.value = references.value.filter(r => r.id !== ref.id)
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}
</script>

<style scoped>
.reference-library-page { padding: 24px; max-width: 1200px; margin: 0 auto; }
.page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 32px; flex-wrap: wrap; gap: 16px;
}
.header-left { display: flex; align-items: center; gap: 12px; }
.page-title { font-size: 20px; margin: 0; font-weight: 600; }
.page-main { min-height: 400px; }
.reference-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }
.reference-card { cursor: pointer; transition: box-shadow .2s; }
.reference-card:hover { box-shadow: var(--el-box-shadow-light); }
.ref-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; }
.ref-title { font-size: 16px; font-weight: 600; margin: 0; flex: 1; }
.ref-meta { font-size: 13px; color: var(--el-text-color-secondary); margin: 0 0 8px; }
.ref-stats { font-size: 13px; color: var(--el-text-color-regular); margin-bottom: 12px; }
.ref-actions { display: flex; gap: 4px; }
</style>
