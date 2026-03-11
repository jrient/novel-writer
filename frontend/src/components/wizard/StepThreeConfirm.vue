<template>
  <div class="step-three">
    <div class="step-header">
      <h2>选择风格参考</h2>
      <p class="step-desc">选择参考小说，AI 将学习其文风进行创作（可选）</p>
    </div>

    <!-- 参考小说列表 -->
    <div class="reference-section">
      <div class="section-header">
        <h3>参考小说库</h3>
        <el-button text @click="refreshReferences">
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>

      <div v-if="loading" class="loading-state">
        <el-skeleton :rows="3" animated />
      </div>

      <div v-else-if="references.length === 0" class="empty-state">
        <el-empty description="暂无参考小说">
          <el-button type="primary" @click="goToReferenceUpload">上传参考小说</el-button>
        </el-empty>
      </div>

      <div v-else class="reference-grid">
        <div
          v-for="ref in references"
          :key="ref.id"
          class="reference-card"
          :class="{ selected: isSelected(ref.id) }"
          @click="toggleSelect(ref.id)"
        >
          <div class="card-header">
            <h4 class="ref-title">{{ ref.title }}</h4>
            <el-icon v-if="isSelected(ref.id)" class="check-icon"><Check /></el-icon>
          </div>
          <p class="ref-author" v-if="ref.author">{{ ref.author }}</p>
          <div class="ref-meta">
            <el-tag v-if="ref.genre" size="small" effect="plain">{{ ref.genre }}</el-tag>
            <span v-if="ref.total_chars" class="word-count">{{ formatWordCount(ref.total_chars) }} 字</span>
          </div>
          <p class="ref-style" v-if="ref.writing_style">{{ ref.writing_style.slice(0, 100) }}...</p>
        </div>
      </div>
    </div>

    <!-- 选中预览 -->
    <div v-if="wizardStore.selectedReferences.length > 0" class="selected-preview">
      <h4>已选择的风格参考 ({{ wizardStore.selectedReferences.length }})</h4>
      <div class="selected-tags">
        <el-tag
          v-for="id in wizardStore.selectedReferences"
          :key="id"
          closable
          @close="toggleSelect(id)"
        >
          {{ getReferenceName(id) }}
        </el-tag>
      </div>
    </div>

    <!-- 确认信息 -->
    <div class="confirm-section">
      <h3>创作信息确认</h3>
      <div class="confirm-info">
        <div class="info-item">
          <span class="label">标题</span>
          <span class="value">{{ wizardStore.ideaData.title }}</span>
        </div>
        <div class="info-item">
          <span class="label">类型</span>
          <span class="value">{{ wizardStore.ideaData.genre || '未指定' }}</span>
        </div>
        <div class="info-item">
          <span class="label">目标字数</span>
          <span class="value">{{ wizardStore.ideaData.target_word_count.toLocaleString() }} 字</span>
        </div>
        <div class="info-item">
          <span class="label">章节数</span>
          <span class="value">{{ wizardStore.outline.length }} 章</span>
        </div>
        <div class="info-item">
          <span class="label">角色数</span>
          <span class="value">{{ wizardStore.characters.length }} 个</span>
        </div>
      </div>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回编辑</el-button>
      <el-button type="primary" size="large" @click="handleCreate" :loading="wizardStore.creating">
        创建项目
        <el-icon class="el-icon--right"><Check /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Check, Refresh } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'

interface ReferenceNovel {
  id: number
  title: string
  author?: string
  genre?: string
  total_chars: number
  writing_style?: string
}

const router = useRouter()
const wizardStore = useWizardStore()

const loading = ref(false)
const references = ref<ReferenceNovel[]>([])

onMounted(() => {
  fetchReferences()
})

async function fetchReferences() {
  loading.value = true
  try {
    const resp = await fetch('/api/v1/references/')
    if (resp.ok) {
      const data = await resp.json()
      references.value = data.items || data
    }
  } catch (e) {
    console.error('获取参考小说列表失败:', e)
  } finally {
    loading.value = false
  }
}

function refreshReferences() {
  fetchReferences()
}

function goToReferenceUpload() {
  // 可以跳转到参考小说管理页面
  router.push('/projects')
}

function isSelected(id: number) {
  return wizardStore.selectedReferences.includes(id)
}

function toggleSelect(id: number) {
  const index = wizardStore.selectedReferences.indexOf(id)
  if (index > -1) {
    wizardStore.selectedReferences.splice(index, 1)
  } else {
    wizardStore.selectedReferences.push(id)
  }
}

function getReferenceName(id: number) {
  const ref = references.value.find(r => r.id === id)
  return ref?.title || `参考 #${id}`
}

function formatWordCount(count: number) {
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + ' 万'
  }
  return count.toLocaleString()
}

async function handleCreate() {
  try {
    await wizardStore.createProject()
    wizardStore.nextStep()
  } catch (e: any) {
    console.error('创建项目失败:', e)
  }
}
</script>

<style scoped>
.step-three {
  max-width: 900px;
  margin: 0 auto;
}

.step-header {
  text-align: center;
  margin-bottom: 32px;
}

.step-header h2 {
  font-size: 24px;
  font-weight: 600;
  color: #2C2C2C;
  margin-bottom: 8px;
  font-family: 'Noto Serif SC', serif;
}

.step-desc {
  font-size: 14px;
  color: #7A7A7A;
}

.reference-section {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
  margin-bottom: 24px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
}

.loading-state {
  padding: 24px;
}

.empty-state {
  padding: 40px 0;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

.reference-card {
  padding: 16px;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.reference-card:hover {
  border-color: #6B7B8D;
}

.reference-card.selected {
  border-color: #6B7B8D;
  background: rgba(107, 123, 141, 0.05);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.ref-title {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
  margin: 0;
}

.check-icon {
  color: #6B7B8D;
  font-size: 18px;
}

.ref-author {
  font-size: 12px;
  color: #9E9E9E;
  margin: 4px 0 8px;
}

.ref-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.word-count {
  font-size: 12px;
  color: #7A7A7A;
}

.ref-style {
  font-size: 12px;
  color: #7A7A7A;
  line-height: 1.5;
  margin: 0;
}

.selected-preview {
  background: rgba(107, 123, 141, 0.05);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 24px;
}

.selected-preview h4 {
  font-size: 13px;
  font-weight: 500;
  color: #6B7B8D;
  margin: 0 0 12px;
}

.selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.confirm-section {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
}

.confirm-section h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0 0 20px;
}

.confirm-info {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item .label {
  font-size: 12px;
  color: #9E9E9E;
}

.info-item .value {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>