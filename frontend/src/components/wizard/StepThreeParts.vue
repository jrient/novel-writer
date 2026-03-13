<template>
  <div class="step-three">
    <div class="step-header">
      <h2>生成故事部分</h2>
      <p class="step-desc">选择一个地图，AI 为其生成详细的故事部分划分</p>
    </div>

    <!-- 地图选择 -->
    <div class="map-selector">
      <div class="selector-label">选择地图：</div>
      <div class="map-tabs">
        <div
          v-for="mapItem in wizardStore.maps"
          :key="mapItem.id"
          class="map-tab"
          :class="{ active: wizardStore.selectedMapId === mapItem.id }"
          @click="selectMap(mapItem.id || '')"
        >
          {{ mapItem.name }}
          <span class="parts-badge">{{ mapItem.parts.length }}</span>
        </div>
      </div>
    </div>

    <!-- 生成状态 -->
    <div v-if="wizardStore.generatingParts" class="generating-state">
      <div class="generating-animation">
        <el-icon class="rotating" :size="48" color="#6B7B8D"><Loading /></el-icon>
      </div>
      <p class="generating-text">正在为「{{ selectedMapName }}」生成部分...</p>
    </div>

    <!-- 部分列表 -->
    <div v-else-if="currentMap && currentMap.parts.length > 0" class="parts-section">
      <div class="section-header">
        <h3>{{ currentMap.name }} - 故事部分</h3>
        <div class="header-actions">
          <el-button text @click="handleRegenerate">
            <el-icon><Refresh /></el-icon> 重新生成
          </el-button>
        </div>
      </div>

      <div class="parts-list">
        <div
          v-for="(part, index) in currentMap.parts"
          :key="part.id"
          class="part-card"
        >
          <div class="part-header">
            <div class="part-number">{{ index + 1 }}</div>
            <el-input v-model="part.name" placeholder="部分名称" class="part-name-input" />
          </div>
          <el-input
            v-model="part.summary"
            type="textarea"
            :rows="2"
            placeholder="部分概要"
            class="part-summary-input"
          />
          <div class="part-meta">
            <el-input-number
              v-model="part.chapters.length"
              :min="0"
              :max="20"
              size="small"
              controls-position="right"
            />
            <span class="chapters-label">章节数</span>
          </div>
        </div>
      </div>

      <!-- 添加部分按钮 -->
      <div class="add-part-btn" @click="addNewPart">
        <el-icon><Plus /></el-icon>
        添加部分
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else-if="wizardStore.selectedMapId" class="empty-state">
      <el-empty description="暂无部分">
        <el-button type="primary" @click="startGenerate">
          生成故事部分
        </el-button>
      </el-empty>
    </div>

    <div v-else class="empty-state">
      <el-empty description="请先选择一个地图" />
    </div>

    <!-- 修改意见 -->
    <div v-if="currentMap && currentMap.parts.length > 0" class="revision-section">
      <el-input
        v-model="revisionRequest"
        type="textarea"
        :rows="2"
        placeholder="如果有修改意见，输入后点击「修改部分」..."
      />
      <el-button
        v-if="revisionRequest"
        type="primary"
        text
        @click="handleRevision"
        :loading="wizardStore.generatingParts"
      >
        修改部分
      </el-button>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回修改</el-button>
      <el-button
        type="primary"
        size="large"
        @click="handleNext"
        :disabled="totalParts === 0"
      >
        下一步：生成角色
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Loading, Refresh, Plus, ArrowRight } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import { ElMessage } from 'element-plus'
import { generateUUID } from '@/api/wizard'

const wizardStore = useWizardStore()
const revisionRequest = ref('')

const currentMap = computed(() => wizardStore.selectedMap)
const selectedMapName = computed(() => currentMap.value?.name || '')

const totalParts = computed(() => {
  let count = 0
  for (const mapItem of wizardStore.maps) {
    count += mapItem.parts.length
  }
  return count
})

function selectMap(mapId: string) {
  wizardStore.selectedMapId = mapId
}

async function startGenerate() {
  if (!wizardStore.selectedMapId) {
    ElMessage.warning('请先选择一个地图')
    return
  }
  try {
    await wizardStore.generatePartsForMap(wizardStore.selectedMapId)
    ElMessage.success('部分生成成功')
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  }
}

async function handleRegenerate() {
  if (!wizardStore.selectedMapId) return
  revisionRequest.value = ''
  try {
    await wizardStore.generatePartsForMap(wizardStore.selectedMapId)
    ElMessage.success('部分重新生成成功')
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  }
}

async function handleRevision() {
  if (!wizardStore.selectedMapId || !revisionRequest.value.trim()) return
  try {
    await wizardStore.generatePartsForMap(wizardStore.selectedMapId, revisionRequest.value)
    revisionRequest.value = ''
    ElMessage.success('部分修改成功')
  } catch (e: any) {
    ElMessage.error(e.message || '修改失败')
  }
}

function addNewPart() {
  if (!wizardStore.selectedMapId) return
  const currentParts = currentMap.value?.parts || []
  wizardStore.addPartToMap(wizardStore.selectedMapId, {
    id: generateUUID(),
    name: `第${currentParts.length + 1}部分`,
    summary: '',
    chapters: [],
    character_ids: [],
  })
}

function handleNext() {
  wizardStore.nextStep()
}
</script>

<style scoped>
.step-three {
  max-width: 900px;
  margin: 0 auto;
}

.step-header {
  text-align: center;
  margin-bottom: 24px;
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

.map-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.selector-label {
  font-size: 14px;
  font-weight: 500;
  color: #2C2C2C;
}

.map-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.map-tab {
  padding: 8px 16px;
  border: 1px solid #E0DFDC;
  border-radius: 20px;
  font-size: 14px;
  color: #7A7A7A;
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 8px;
}

.map-tab:hover {
  border-color: #6B7B8D;
}

.map-tab.active {
  border-color: #6B7B8D;
  background: #6B7B8D;
  color: white;
}

.parts-badge {
  background: rgba(107, 123, 141, 0.2);
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
}

.map-tab.active .parts-badge {
  background: rgba(255, 255, 255, 0.2);
}

.generating-state {
  text-align: center;
  padding: 60px 20px;
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
}

.generating-animation {
  margin-bottom: 24px;
}

.rotating {
  animation: rotate 1.5s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.generating-text {
  font-size: 18px;
  font-weight: 500;
  color: #2C2C2C;
}

.parts-section {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
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

.parts-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.part-card {
  padding: 16px;
  border: 1px solid #E0DFDC;
  border-radius: 12px;
}

.part-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.part-number {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #6B7B8D;
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 500;
  flex-shrink: 0;
}

.part-name-input {
  flex: 1;
}

.part-summary-input {
  margin-bottom: 12px;
}

.part-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chapters-label {
  font-size: 14px;
  color: #9E9E9E;
}

.add-part-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  border: 2px dashed #E0DFDC;
  border-radius: 12px;
  cursor: pointer;
  color: #9E9E9E;
  transition: all 0.2s ease;
  margin-top: 16px;
}

.add-part-btn:hover {
  border-color: #6B7B8D;
  color: #6B7B8D;
}

.empty-state {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 40px;
}

.revision-section {
  margin-top: 20px;
  display: flex;
  gap: 12px;
  align-items: flex-end;
}

.revision-section .el-input {
  flex: 1;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>