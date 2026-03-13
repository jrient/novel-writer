<template>
  <div class="step-seven">
    <div class="success-state">
      <div class="success-icon">
        <el-icon :size="64" color="#6B7B8D"><CircleCheck /></el-icon>
      </div>
      <h2>项目创建成功！</h2>
      <p class="success-desc">你的小说项目已准备就绪，可以开始创作了</p>

      <div class="project-summary">
        <div class="summary-item">
          <span class="summary-label">项目名称</span>
          <span class="summary-value">{{ wizardStore.ideaData.title }}</span>
        </div>
        <div class="summary-stats">
          <div class="stat">
            <span class="stat-value">{{ wizardStore.maps.length }}</span>
            <span class="stat-label">地图</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ wizardStore.totalChapters }}</span>
            <span class="stat-label">章节</span>
          </div>
          <div class="stat">
            <span class="stat-value">{{ wizardStore.characters.length }}</span>
            <span class="stat-label">角色</span>
          </div>
        </div>
      </div>

      <div class="next-steps">
        <h4>接下来你可以：</h4>
        <div class="step-options">
          <div class="option-card" @click="goToWorkbench">
            <el-icon :size="32"><Edit /></el-icon>
            <div class="option-content">
              <h5>进入工作台</h5>
              <p>查看大纲和角色，开始撰写章节</p>
            </div>
            <el-icon class="arrow"><ArrowRight /></el-icon>
          </div>
          <div class="option-card" @click="createNew">
            <el-icon :size="32"><Plus /></el-icon>
            <div class="option-content">
              <h5>创建新项目</h5>
              <p>开始另一个创作项目</p>
            </div>
            <el-icon class="arrow"><ArrowRight /></el-icon>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleCheck, Edit, Plus, ArrowRight } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useWizardStore } from '@/stores/wizard'

const router = useRouter()
const wizardStore = useWizardStore()

function goToWorkbench() {
  const projectId = wizardStore.createdProjectId
  console.log('goToWorkbench called, projectId:', projectId)
  if (projectId) {
    console.log('Navigating to:', `/project/${projectId}`)
    router.push(`/project/${projectId}`)
  } else {
    console.error('No projectId found!')
  }
}

function createNew() {
  wizardStore.reset()
}
</script>

<style scoped>
.step-seven {
  max-width: 600px;
  margin: 0 auto;
}

.success-state {
  text-align: center;
  padding: 40px 0;
}

.success-icon {
  margin-bottom: 24px;
}

.success-state h2 {
  font-size: 28px;
  font-weight: 600;
  color: #2C2C2C;
  margin-bottom: 8px;
  font-family: 'Noto Serif SC', serif;
}

.success-desc {
  font-size: 14px;
  color: #7A7A7A;
  margin-bottom: 32px;
}

.project-summary {
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
  padding: 24px;
  margin-bottom: 32px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid #E0DFDC;
}

.summary-label {
  font-size: 12px;
  color: #9E9E9E;
}

.summary-value {
  font-size: 18px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
}

.summary-stats {
  display: flex;
  justify-content: space-around;
}

.stat {
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

.next-steps h4 {
  font-size: 14px;
  font-weight: 500;
  color: #7A7A7A;
  margin-bottom: 16px;
}

.step-options {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.option-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 20px 24px;
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.option-card:hover {
  border-color: #6B7B8D;
  transform: translateX(4px);
}

.option-card .el-icon:first-child {
  color: #6B7B8D;
}

.option-content {
  flex: 1;
  text-align: left;
}

.option-content h5 {
  font-size: 15px;
  font-weight: 500;
  color: #2C2C2C;
  margin: 0 0 4px;
}

.option-content p {
  font-size: 13px;
  color: #9E9E9E;
  margin: 0;
}

.arrow {
  color: #9E9E9E;
}
</style>