<template>
  <div class="step-two">
    <div class="step-header">
      <h2>生成地图大纲</h2>
      <p class="step-desc">AI 将根据你的故事构思，生成主要场景地图</p>
    </div>

    <!-- 生成状态 -->
    <div v-if="wizardStore.generatingMaps" class="generating-state">
      <div class="generating-animation">
        <el-icon class="rotating" :size="48" color="#6B7B8D"><Loading /></el-icon>
      </div>
      <p class="generating-text">正在生成地图大纲...</p>
      <p class="generating-hint">AI 正在分析你的故事构思，设计主要场景</p>
    </div>

    <!-- 地图列表 -->
    <div v-else-if="wizardStore.maps.length > 0" class="maps-section">
      <div class="section-header">
        <h3>场景地图</h3>
        <div class="header-actions">
          <el-button text @click="handleRegenerate">
            <el-icon><Refresh /></el-icon> 重新生成
          </el-button>
        </div>
      </div>

      <div class="maps-grid">
        <div
          v-for="(mapItem, index) in wizardStore.maps"
          :key="mapItem.id"
          class="map-card"
          :class="{ selected: wizardStore.selectedMapId === mapItem.id }"
          @click="selectMap(mapItem.id || '')"
        >
          <div class="map-header">
            <div class="map-number">{{ index + 1 }}</div>
            <el-input
              v-model="mapItem.name"
              placeholder="地图名称"
              class="map-name-input"
            />
          </div>
          <el-input
            v-model="mapItem.description"
            type="textarea"
            :rows="2"
            placeholder="地图描述"
            class="map-desc-input"
          />
          <div class="map-meta">
            <span class="parts-count">{{ mapItem.parts.length }} 个部分</span>
          </div>
        </div>
      </div>

      <!-- 添加地图按钮 -->
      <div class="add-map-card" @click="addNewMap">
        <el-icon :size="32"><Plus /></el-icon>
        <span>添加地图</span>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-else class="empty-state">
      <el-empty description="暂无地图">
        <el-button type="primary" @click="startGenerate">
          生成地图大纲
        </el-button>
      </el-empty>
    </div>

    <!-- 修改意见 -->
    <div v-if="wizardStore.maps.length > 0" class="revision-section">
      <el-input
        v-model="revisionRequest"
        type="textarea"
        :rows="2"
        placeholder="如果有修改意见，输入后点击「修改大纲」..."
      />
      <el-button
        v-if="revisionRequest"
        type="primary"
        text
        @click="handleRevision"
        :loading="wizardStore.generatingMaps"
      >
        修改大纲
      </el-button>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回修改</el-button>
      <el-button
        type="primary"
        size="large"
        @click="handleNext"
        :disabled="wizardStore.maps.length === 0"
      >
        下一步：生成部分
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Loading, Refresh, Plus, ArrowRight } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import { ElMessage } from 'element-plus'
import { generateUUID } from '@/api/wizard'

const wizardStore = useWizardStore()
const revisionRequest = ref('')

async function startGenerate() {
  try {
    await wizardStore.generateMaps()
    ElMessage.success('地图生成成功')
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  }
}

async function handleRegenerate() {
  revisionRequest.value = ''
  await startGenerate()
}

async function handleRevision() {
  if (!revisionRequest.value.trim()) return
  try {
    await wizardStore.generateMaps(revisionRequest.value)
    revisionRequest.value = ''
    ElMessage.success('地图修改成功')
  } catch (e: any) {
    ElMessage.error(e.message || '修改失败')
  }
}

function selectMap(mapId: string) {
  wizardStore.selectedMapId = mapId
}

function addNewMap() {
  wizardStore.maps.push({
    id: generateUUID(),
    name: `新地图`,
    description: '',
    parts: [],
  })
}

function handleNext() {
  wizardStore.nextStep()
}
</script>

<style scoped>
.step-two {
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
  margin-bottom: 8px;
}

.generating-hint {
  font-size: 14px;
  color: #9E9E9E;
}

.maps-section {
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

.maps-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.map-card {
  padding: 16px;
  border: 1px solid #E0DFDC;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.map-card:hover {
  border-color: #6B7B8D;
}

.map-card.selected {
  border-color: #6B7B8D;
  background: rgba(107, 123, 141, 0.05);
}

.map-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.map-number {
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

.map-name-input {
  flex: 1;
}

.map-name-input :deep(.el-input__wrapper) {
  padding: 4px 8px;
}

.map-desc-input :deep(.el-textarea__inner) {
  min-height: 60px;
}

.map-meta {
  margin-top: 8px;
  font-size: 12px;
  color: #9E9E9E;
}

.add-map-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px;
  border: 2px dashed #E0DFDC;
  border-radius: 12px;
  cursor: pointer;
  color: #9E9E9E;
  transition: all 0.2s ease;
}

.add-map-card:hover {
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