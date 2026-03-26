<template>
  <div class="expansion-create-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.push('/expansion')">返回列表</el-button>
          <h1 class="page-title">新建扩写项目</h1>
        </div>
      </div>
    </header>

    <main class="page-main">
      <el-card class="create-card">
        <!-- Tabs for different input methods -->
        <el-tabs v-model="activeTab" class="input-tabs">
          <!-- Tab 1: Upload file -->
          <el-tab-pane label="上传文件" name="upload">
            <div class="upload-area">
              <el-upload
                ref="uploadRef"
                class="file-upload"
                drag
                :auto-upload="false"
                :show-file-list="true"
                :limit="1"
                accept=".txt,.md,.docx"
                @change="handleFileChange"
              >
                <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
                <div class="el-upload__text">
                  拖拽文件到此处，或 <em>点击上传</em>
                </div>
                <template #tip>
                  <div class="el-upload__tip">
                    支持 .txt, .md, .docx 格式，最大 30000 字
                  </div>
                </template>
              </el-upload>

              <div v-if="fileContent" class="file-preview">
                <div class="preview-header">
                  <span>文件预览</span>
                  <span class="char-count">{{ fileContent.length.toLocaleString() }} 字</span>
                </div>
                <div class="preview-content">{{ fileContent.slice(0, 500) }}{{ fileContent.length > 500 ? '...' : '' }}</div>
              </div>
            </div>
          </el-tab-pane>

          <!-- Tab 2: Import from platform -->
          <el-tab-pane label="从平台导入" name="import">
            <div class="import-area">
              <el-button type="primary" plain @click="showImportDialog = true">
                <el-icon><Download /></el-icon>
                选择导入源
              </el-button>

              <div v-if="importSource" class="import-info">
                <el-tag :type="importSource.type === 'novel' ? 'success' : 'warning'">
                  {{ importSource.type === 'novel' ? '小说' : '剧本' }}：{{ importSource.title }}
                </el-tag>
                <span class="word-count">{{ importSource.wordCount?.toLocaleString() || 0 }} 字</span>
              </div>
            </div>
          </el-tab-pane>

          <!-- Tab 3: Manual input -->
          <el-tab-pane label="手动输入" name="manual">
            <div class="manual-area">
              <el-input
                v-model="manualText"
                type="textarea"
                :rows="12"
                placeholder="请输入需要扩写的文本内容..."
                maxlength="30000"
                show-word-limit
              />
            </div>
          </el-tab-pane>
        </el-tabs>

        <!-- Common settings -->
        <el-divider />

        <el-form
          ref="formRef"
          :model="formData"
          :rules="formRules"
          label-width="100px"
          class="settings-form"
        >
          <el-form-item label="项目名称" prop="title">
            <el-input v-model="formData.title" placeholder="请输入项目名称" maxlength="200" />
          </el-form-item>

          <el-form-item label="扩写深度" prop="expansion_level">
            <el-radio-group v-model="formData.expansion_level">
              <el-radio-button value="light">轻度扩写</el-radio-button>
              <el-radio-button value="medium">中度扩写</el-radio-button>
              <el-radio-button value="deep">深度扩写</el-radio-button>
            </el-radio-group>
            <div class="form-tip">
              轻度: 保留原文约70% | 中度: 保留原文约50% | 深度: 保留原文约30%
            </div>
          </el-form-item>

          <el-form-item label="目标字数">
            <el-input-number
              v-model="formData.target_word_count"
              :min="0"
              :max="100000"
              :step="1000"
              placeholder="可选"
            />
            <span class="input-hint">留空则根据扩写深度自动计算</span>
          </el-form-item>

          <el-form-item label="执行模式" prop="execution_mode">
            <el-radio-group v-model="formData.execution_mode">
              <el-radio-button value="auto">自动扩写</el-radio-button>
              <el-radio-button value="step_by_step">逐步确认</el-radio-button>
            </el-radio-group>
            <div class="form-tip">
              自动: 批量完成所有分段扩写 | 逐步: 每段扩写前需确认
            </div>
          </el-form-item>
        </el-form>

        <!-- Submit -->
        <div class="submit-bar">
          <el-button @click="router.push('/expansion')">取消</el-button>
          <el-button
            type="primary"
            :loading="submitting"
            :disabled="!canSubmit"
            @click="handleSubmit"
          >
            创建项目
          </el-button>
        </div>
      </el-card>
    </main>

    <!-- Import Dialog -->
    <ImportSourceDialog
      v-model="showImportDialog"
      @import="handleImportSelect"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowLeft, UploadFilled, Download } from '@element-plus/icons-vue'
import type { FormInstance, FormRules, UploadFile } from 'element-plus'
import { useExpansionStore } from '@/stores/expansion'
import ImportSourceDialog from '@/components/expansion/ImportSourceDialog.vue'

const router = useRouter()
const expansionStore = useExpansionStore()

const activeTab = ref<'upload' | 'import' | 'manual'>('upload')
const uploadRef = ref()
const formRef = ref<FormInstance>()

// Form data
const formData = ref({
  title: '',
  expansion_level: 'medium' as 'light' | 'medium' | 'deep',
  target_word_count: null as number | null,
  execution_mode: 'auto' as 'auto' | 'step_by_step',
})

const formRules: FormRules = {
  title: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
}

// Upload tab state
const selectedFile = ref<File | null>(null)
const fileContent = ref('')

// Import tab state
const showImportDialog = ref(false)
const importSource = ref<{
  type: 'novel' | 'drama'
  projectId: number
  title: string
  chapterIds?: number[]
  wordCount?: number
} | null>(null)

// Manual tab state
const manualText = ref('')

// Submit state
const submitting = ref(false)

// Computed
const canSubmit = computed(() => {
  if (!formData.value.title.trim()) return false

  if (activeTab.value === 'upload') {
    return fileContent.value.length > 0 && fileContent.value.length <= 30000
  }

  if (activeTab.value === 'import') {
    return importSource.value !== null
  }

  if (activeTab.value === 'manual') {
    return manualText.value.trim().length > 0 && manualText.value.length <= 30000
  }

  return false
})

// Methods
async function handleFileChange(uploadFile: UploadFile) {
  const file = uploadFile.raw
  if (!file) return

  selectedFile.value = file

  // Read file content
  try {
    const text = await readFileContent(file)
    fileContent.value = text

    // Auto-fill title from filename
    if (!formData.value.title) {
      formData.value.title = file.name.replace(/\.(txt|md|docx)$/, '')
    }

    if (text.length > 30000) {
      ElMessage.warning('文件内容超过 30000 字限制，将截取前 30000 字')
      fileContent.value = text.slice(0, 30000)
    }
  } catch (err) {
    ElMessage.error('读取文件失败')
    fileContent.value = ''
  }
}

async function readFileContent(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()

    reader.onload = (e) => {
      const text = e.target?.result as string
      resolve(text)
    }

    reader.onerror = () => reject(new Error('读取失败'))

    // For .docx, we'd need a library like mammoth.js
    // For now, just read as text (works for .txt and .md)
    if (file.name.endsWith('.docx')) {
      // TODO: Handle docx with mammoth.js
      reject(new Error('暂不支持 .docx 格式'))
    } else {
      reader.readAsText(file)
    }
  })
}

function handleImportSelect(data: { source: 'novel' | 'drama'; projectId: number; chapterIds?: number[] }) {
  importSource.value = {
    type: data.source,
    projectId: data.projectId,
    title: data.source === 'novel'
      ? (novelProjects.find(p => p.id === data.projectId)?.title || '')
      : (dramaProjects.find(p => p.id === data.projectId)?.title || ''),
    chapterIds: data.chapterIds,
  }

  // Auto-fill title
  if (!formData.value.title && importSource.value.title) {
    formData.value.title = `${importSource.value.title} - 扩写`
  }
}

// Need to fetch project lists for title lookup
const novelProjects = ref<{ id: number; title: string }[]>([])
const dramaProjects = ref<{ id: number; title: string }[]>([])

async function handleSubmit() {
  if (!formRef.value) return

  await formRef.value.validate()

  submitting.value = true

  try {
    let project

    if (activeTab.value === 'upload') {
      if (!selectedFile.value) return
      project = await expansionStore.uploadProject(
        selectedFile.value,
        formData.value.title,
        formData.value.expansion_level,
        formData.value.target_word_count || undefined,
        undefined,
        formData.value.execution_mode,
      )
    } else if (activeTab.value === 'import' && importSource.value) {
      if (importSource.value.type === 'novel') {
        project = await expansionStore.importFromNovelProject({
          project_id: importSource.value.projectId,
          chapter_ids: importSource.value.chapterIds || [],
          title: formData.value.title,
        })
      } else {
        project = await expansionStore.importFromDramaProject({
          project_id: importSource.value.projectId,
          title: formData.value.title,
        })
      }
    } else if (activeTab.value === 'manual') {
      project = await expansionStore.createProject({
        title: formData.value.title,
        source_type: 'manual',
        original_text: manualText.value,
        expansion_level: formData.value.expansion_level,
        target_word_count: formData.value.target_word_count || undefined,
        execution_mode: formData.value.execution_mode,
      })
    }

    if (project) {
      ElMessage.success('创建成功')
      router.push(`/expansion/analyze/${project.id}`)
    }
  } catch (err: unknown) {
    const error = err as { response?: { data?: { detail?: string } } }
    ElMessage.error(error.response?.data?.detail || '创建失败')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.expansion-create-page {
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
  max-width: 900px;
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

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
  font-family: 'Noto Serif SC', serif;
}

.page-main {
  max-width: 900px;
  margin: 0 auto;
  padding: 32px;
}

.create-card {
  border-radius: 14px;
  border: 1px solid #E0DFDC;
}

.input-tabs {
  margin-bottom: 20px;
}

.upload-area {
  min-height: 200px;
}

.file-upload {
  width: 100%;
}

.file-upload :deep(.el-upload-dragger) {
  border: 2px dashed #D9D9D9;
  border-radius: 8px;
  background: #FAFAFA;
  transition: all 0.3s;
}

.file-upload :deep(.el-upload-dragger:hover) {
  border-color: #6B7B8D;
}

.file-preview {
  margin-top: 16px;
  padding: 12px;
  background: #F5F5F5;
  border-radius: 8px;
}

.preview-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  color: #7A7A7A;
}

.char-count {
  font-weight: 500;
  color: #6B7B8D;
}

.preview-content {
  font-size: 13px;
  color: #5C5C5C;
  line-height: 1.6;
  white-space: pre-wrap;
}

.import-area {
  min-height: 200px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
}

.import-info {
  display: flex;
  align-items: center;
  gap: 12px;
}

.word-count {
  font-size: 13px;
  color: #9E9E9E;
}

.manual-area {
  min-height: 200px;
}

.settings-form {
  max-width: 600px;
}

.form-tip {
  font-size: 12px;
  color: #9E9E9E;
  margin-top: 4px;
}

.input-hint {
  font-size: 12px;
  color: #9E9E9E;
  margin-left: 12px;
}

.submit-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid #ECEAE6;
}

@media (max-width: 768px) {
  .page-main { padding: 16px; }
  .page-header { padding: 0 16px; }
}
</style>