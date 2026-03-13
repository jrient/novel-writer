<template>
  <div class="step-four">
    <div class="step-header">
      <h2>生成角色</h2>
      <p class="step-desc">AI 将根据故事大纲生成主要角色，角色可以在多个部分复用</p>
    </div>

    <!-- 生成状态 -->
    <div v-if="wizardStore.generatingCharacters" class="generating-state">
      <div class="generating-animation">
        <el-icon class="rotating" :size="48" color="#6B7B8D"><Loading /></el-icon>
      </div>
      <p class="generating-text">正在生成角色设定...</p>
    </div>

    <!-- 角色列表 -->
    <div v-else class="characters-section">
      <div class="section-header">
        <h3>角色库 ({{ wizardStore.characters.length }})</h3>
        <div class="header-actions">
          <el-button type="primary" text @click="handleGenerate">
            <el-icon><MagicStick /></el-icon> 生成角色
          </el-button>
          <el-button text @click="addNewCharacter">
            <el-icon><Plus /></el-icon> 手动添加
          </el-button>
        </div>
      </div>

      <div v-if="wizardStore.characters.length === 0" class="empty-characters">
        <el-empty description="暂无角色">
          <el-button type="primary" @click="handleGenerate">生成角色</el-button>
        </el-empty>
      </div>

      <div v-else class="characters-list">
        <div
          v-for="(char, index) in wizardStore.characters"
          :key="index"
          class="character-card"
        >
          <div class="char-main">
            <div class="char-header">
              <div class="char-title">
                <el-tag :type="getRoleTagType(char.role_type)" size="small">
                  {{ getRoleTypeName(char.role_type) }}
                </el-tag>
                <el-input v-model="char.name" placeholder="角色名称" class="name-input" />
              </div>
              <el-button
                type="danger"
                text
                size="small"
                @click="removeCharacter(index)"
              >
                <el-icon><Delete /></el-icon> 删除
              </el-button>
            </div>

            <div class="char-basic-info">
              <el-row :gutter="16">
                <el-col :span="8">
                  <div class="info-item">
                    <label>性别</label>
                    <el-input v-model="char.gender" placeholder="性别" size="small" />
                  </div>
                </el-col>
                <el-col :span="8">
                  <div class="info-item">
                    <label>年龄</label>
                    <el-input v-model="char.age" placeholder="年龄" size="small" />
                  </div>
                </el-col>
                <el-col :span="8">
                  <div class="info-item">
                    <label>职业</label>
                    <el-input v-model="char.occupation" placeholder="职业" size="small" />
                  </div>
                </el-col>
              </el-row>
            </div>
          </div>

          <div class="char-details">
            <div class="detail-row">
              <label>性格特征</label>
              <el-input
                v-model="char.personality_traits"
                type="textarea"
                :rows="3"
                placeholder="性格特征"
                size="small"
              />
            </div>
            <div class="detail-row">
              <label>外貌描述</label>
              <el-input
                v-model="char.appearance"
                type="textarea"
                :rows="3"
                placeholder="外貌描述"
                size="small"
              />
            </div>
            <div class="detail-row">
              <label>背景故事</label>
              <el-input
                v-model="char.background"
                type="textarea"
                :rows="4"
                placeholder="背景故事"
                size="small"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="step-actions">
      <el-button size="large" @click="wizardStore.prevStep">返回修改</el-button>
      <el-button
        type="primary"
        size="large"
        @click="handleNext"
        :disabled="wizardStore.characters.length === 0"
      >
        下一步：添加笔记
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Loading, MagicStick, Plus, Delete, ArrowRight } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import { ElMessage } from 'element-plus'
import { generateUUID } from '@/api/wizard'

const wizardStore = useWizardStore()

async function handleGenerate() {
  try {
    await wizardStore.generateCharactersForAllParts()
    ElMessage.success('角色生成成功')
  } catch (e: any) {
    ElMessage.error(e.message || '生成失败')
  }
}

function addNewCharacter() {
  wizardStore.addCharacterItem({
    id: generateUUID(),
    name: '新角色',
    role_type: 'supporting',
    gender: '',
    age: '',
    occupation: '',
    personality_traits: '',
    appearance: '',
    background: '',
    appearances: [],
  })
}

function removeCharacter(index: number) {
  wizardStore.removeCharacterItem(index)
}

function getRoleTagType(roleType: string) {
  switch (roleType) {
    case 'protagonist': return 'success'
    case 'antagonist': return 'danger'
    case 'supporting': return 'warning'
    default: return 'info'
  }
}

function getRoleTypeName(roleType: string) {
  switch (roleType) {
    case 'protagonist': return '主角'
    case 'antagonist': return '反派'
    case 'supporting': return '配角'
    default: return '次要'
  }
}

function handleNext() {
  wizardStore.nextStep()
}
</script>

<style scoped>
.step-four {
  max-width: 1200px;
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
}

.characters-section {
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

.header-actions {
  display: flex;
  gap: 8px;
}

.empty-characters {
  padding: 40px 0;
}

/* 角色列表 - 改为纵向排列 */
.characters-list {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.character-card {
  border: 1px solid #E0DFDC;
  border-radius: 12px;
  background: #FAFAFA;
  overflow: hidden;
}

/* 角色主体信息 */
.char-main {
  padding: 16px 20px;
  border-bottom: 1px solid #E8E8E8;
  background: #FFF;
}

.char-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.char-title {
  display: flex;
  align-items: center;
  gap: 12px;
}

.char-title .name-input {
  width: 200px;
}

.char-title .name-input :deep(.el-input__wrapper) {
  font-weight: 600;
  font-size: 16px;
}

.char-basic-info {
  margin-top: 8px;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.info-item label {
  font-size: 12px;
  color: #909399;
  font-weight: 500;
}

/* 角色详细信息 */
.char-details {
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.detail-row label {
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}

.detail-row :deep(.el-textarea__inner) {
  font-size: 13px;
  line-height: 1.6;
  min-height: auto !important;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>