<template>
  <div class="step-six">
    <div class="step-header">
      <h2>确认创建</h2>
      <p class="step-desc">检查以下信息，确认无误后创建项目</p>
    </div>

    <div class="confirm-section">
      <!-- 基本信息 -->
      <div class="confirm-card">
        <h3>基本信息</h3>
        <div class="info-grid">
          <div class="info-item">
            <span class="info-label">标题</span>
            <span class="info-value">{{ wizardStore.ideaData.title }}</span>
          </div>
          <div class="info-item">
            <span class="info-label">类型</span>
            <span class="info-value">{{ wizardStore.ideaData.genre || '未指定' }}</span>
          </div>
        </div>
        <div class="info-item full">
          <span class="info-label">简介</span>
          <span class="info-value description">{{ wizardStore.ideaData.description }}</span>
        </div>
      </div>

      <!-- 地图统计 -->
      <div class="confirm-card">
        <h3>地图结构</h3>
        <div class="maps-summary">
          <div v-for="mapItem in wizardStore.maps" :key="mapItem.id" class="map-summary-item">
            <div class="map-summary-header">
              <el-icon><Location /></el-icon>
              <span class="map-name">{{ mapItem.name }}</span>
              <span class="parts-count">{{ mapItem.parts.length }} 个部分</span>
            </div>
            <div class="parts-list">
              <div v-for="part in mapItem.parts" :key="part.id" class="part-item">
                <span class="part-name">{{ part.name }}</span>
                <span class="chapters-count">{{ part.chapters?.length || 0 }} 章</span>
              </div>
            </div>
          </div>
        </div>
        <div class="stats-row">
          <div class="stat-item">
            <span class="stat-value">{{ wizardStore.maps.length }}</span>
            <span class="stat-label">地图</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ totalParts }}</span>
            <span class="stat-label">部分</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ wizardStore.totalChapters }}</span>
            <span class="stat-label">章节</span>
          </div>
        </div>
      </div>

      <!-- 角色统计 -->
      <div class="confirm-card">
        <h3>角色库</h3>
        <div class="characters-summary">
          <div v-for="char in wizardStore.characters" :key="char.name" class="char-chip">
            <el-tag :type="getRoleTagType(char.role_type)" size="small">
              {{ getRoleTypeName(char.role_type) }}
            </el-tag>
            <span class="char-name">{{ char.name }}</span>
          </div>
        </div>
        <div class="stats-row">
          <div class="stat-item">
            <span class="stat-value">{{ protagonistCount }}</span>
            <span class="stat-label">主角</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ wizardStore.characters.length - protagonistCount }}</span>
            <span class="stat-label">其他角色</span>
          </div>
        </div>
      </div>

      <!-- 笔记统计 -->
      <div v-if="wizardStore.notes.length > 0" class="confirm-card">
        <h3>笔记</h3>
        <div class="stats-row">
          <div class="stat-item">
            <span class="stat-value">{{ foreshadowingCount }}</span>
            <span class="stat-label">伏笔</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ inspirationCount }}</span>
            <span class="stat-label">灵感</span>
          </div>
          <div class="stat-item">
            <span class="stat-value">{{ noteCount }}</span>
            <span class="stat-label">笔记</span>
          </div>
        </div>
      </div>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回修改</el-button>
      <el-button
        type="primary"
        size="large"
        @click="handleCreate"
        :loading="wizardStore.creating"
      >
        创建项目
        <el-icon class="el-icon--right"><Check /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Location, Check } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import { ElMessage } from 'element-plus'

const wizardStore = useWizardStore()

const totalParts = computed(() => {
  let count = 0
  for (const mapItem of wizardStore.maps) {
    count += mapItem.parts.length
  }
  return count
})

const protagonistCount = computed(() => {
  return wizardStore.characters.filter(c => c.role_type === 'protagonist').length
})

const foreshadowingCount = computed(() => {
  return wizardStore.notes.filter(n => n.note_type === 'foreshadowing').length
})

const inspirationCount = computed(() => {
  return wizardStore.notes.filter(n => n.note_type === 'inspiration').length
})

const noteCount = computed(() => {
  return wizardStore.notes.filter(n => n.note_type === 'note').length
})

function getRoleTagType(roleType: string) {
  switch (roleType) {
    case 'protagonist': return 'success'
    case 'antagonist': return 'danger'
    default: return 'info'
  }
}

function getRoleTypeName(roleType: string) {
  switch (roleType) {
    case 'protagonist': return '主角'
    case 'antagonist': return '反派'
    default: return '配角'
  }
}

async function handleCreate() {
  try {
    await wizardStore.createProjectV2()
    wizardStore.nextStep()
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  }
}
</script>

<style scoped>
.step-six {
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

.confirm-section {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.confirm-card {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
}

.confirm-card h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0 0 16px;
}

.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item.full {
  grid-column: 1 / -1;
  margin-top: 16px;
}

.info-label {
  font-size: 12px;
  color: #9E9E9E;
}

.info-value {
  font-size: 14px;
  color: #2C2C2C;
}

.info-value.description {
  font-size: 13px;
  line-height: 1.6;
  color: #7A7A7A;
}

.maps-summary {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 16px;
}

.map-summary-item {
  padding: 12px;
  background: #FAFAFA;
  border-radius: 8px;
}

.map-summary-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.map-summary-header .el-icon {
  color: #6B7B8D;
}

.map-name {
  font-weight: 500;
  color: #2C2C2C;
}

.parts-count {
  font-size: 12px;
  color: #9E9E9E;
  margin-left: auto;
}

.parts-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.part-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: white;
  border-radius: 4px;
  font-size: 12px;
}

.part-name {
  color: #2C2C2C;
}

.chapters-count {
  color: #9E9E9E;
}

.stats-row {
  display: flex;
  justify-content: center;
  gap: 48px;
  padding-top: 16px;
  border-top: 1px solid #E0DFDC;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: #6B7B8D;
}

.stat-label {
  font-size: 12px;
  color: #9E9E9E;
}

.characters-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
}

.char-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: #FAFAFA;
  border-radius: 4px;
}

.char-chip .char-name {
  font-size: 13px;
  color: #2C2C2C;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>