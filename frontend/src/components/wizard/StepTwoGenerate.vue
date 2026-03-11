<template>
  <div class="step-two">
    <div class="step-header">
      <h2>AI 生成的创作蓝图</h2>
      <p class="step-desc">AI 已根据你的构思生成大纲和角色设定，你可以自由编辑调整</p>
    </div>

    <!-- 加载状态 -->
    <div v-if="wizardStore.generating" class="generating-state">
      <el-icon class="loading-icon" :size="48"><Loading /></el-icon>
      <p class="loading-text">AI 正在创作中...</p>
      <p class="loading-hint">这可能需要 10-30 秒，请耐心等待</p>
    </div>

    <!-- 错误状态 -->
    <el-alert
      v-else-if="wizardStore.generateError"
      :title="wizardStore.generateError"
      type="error"
      show-icon
      class="error-alert"
    >
      <template #default>
        <el-button type="primary" size="small" @click="retryGenerate">重试</el-button>
      </template>
    </el-alert>

    <!-- 生成结果 -->
    <div v-else class="generate-result">
      <!-- 大纲编辑 -->
      <div class="section">
        <div class="section-header">
          <h3>章节大纲</h3>
          <el-button type="primary" text @click="addChapter">
            <el-icon><Plus /></el-icon> 添加章节
          </el-button>
        </div>
        <div class="outline-list">
          <div
            v-for="(item, index) in wizardStore.outline"
            :key="index"
            class="outline-item"
          >
            <div class="item-header">
              <span class="chapter-num">第 {{ item.chapter }} 章</span>
              <el-input
                v-model="item.title"
                placeholder="章节标题"
                class="title-input"
              />
              <el-button type="danger" text @click="removeChapter(index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-input
              v-model="item.summary"
              type="textarea"
              :rows="2"
              placeholder="章节内容概要"
            />
          </div>
        </div>
      </div>

      <!-- 角色编辑 -->
      <div class="section">
        <div class="section-header">
          <h3>角色设定</h3>
          <el-button type="primary" text @click="addCharacter">
            <el-icon><Plus /></el-icon> 添加角色
          </el-button>
        </div>
        <div class="character-list">
          <div
            v-for="(char, index) in wizardStore.characters"
            :key="index"
            class="character-card"
          >
            <div class="char-header">
              <el-input v-model="char.name" placeholder="角色名称" class="name-input" />
              <el-select v-model="char.role_type" class="role-select">
                <el-option label="主角" value="protagonist" />
                <el-option label="反派" value="antagonist" />
                <el-option label="配角" value="supporting" />
                <el-option label="龙套" value="minor" />
              </el-select>
              <el-button type="danger" text @click="removeCharacter(index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <el-row :gutter="16">
              <el-col :span="8">
                <el-input v-model="char.gender" placeholder="性别" />
              </el-col>
              <el-col :span="8">
                <el-input v-model="char.age" placeholder="年龄" />
              </el-col>
              <el-col :span="8">
                <el-input v-model="char.occupation" placeholder="职业/身份" />
              </el-col>
            </el-row>
            <el-input
              v-model="char.personality_traits"
              placeholder="性格特征"
              style="margin-top: 12px"
            />
            <el-input
              v-model="char.appearance"
              placeholder="外貌描写"
              style="margin-top: 12px"
            />
            <el-input
              v-model="char.background"
              type="textarea"
              :rows="2"
              placeholder="背景故事"
              style="margin-top: 12px"
            />
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
        :disabled="wizardStore.generating || wizardStore.outline.length === 0"
      >
        下一步：选择风格
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { ArrowRight, Plus, Delete, Loading } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import type { ChapterOutlineItem, CharacterOutlineItem } from '@/api/wizard'

const wizardStore = useWizardStore()

onMounted(async () => {
  // 如果还没有生成内容，自动开始生成
  if (wizardStore.outline.length === 0 && !wizardStore.generating) {
    await wizardStore.generateOutlineAndCharacters()
  }
})

async function retryGenerate() {
  await wizardStore.generateOutlineAndCharacters()
}

function addChapter() {
  const newItem: ChapterOutlineItem = {
    chapter: wizardStore.outline.length + 1,
    title: '',
    summary: '',
  }
  wizardStore.addOutlineItem(newItem)
}

function removeChapter(index: number) {
  wizardStore.removeOutlineItem(index)
}

function addCharacter() {
  const newChar: CharacterOutlineItem = {
    name: '',
    role_type: 'supporting',
    gender: '',
    age: '',
    occupation: '',
    personality_traits: '',
    appearance: '',
    background: '',
  }
  wizardStore.addCharacterItem(newChar)
}

function removeCharacter(index: number) {
  wizardStore.removeCharacterItem(index)
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
  padding: 80px 0;
  background: white;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
}

.loading-icon {
  color: #6B7B8D;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 18px;
  font-weight: 500;
  color: #2C2C2C;
  margin-top: 16px;
}

.loading-hint {
  font-size: 13px;
  color: #9E9E9E;
  margin-top: 8px;
}

.error-alert {
  margin-bottom: 24px;
}

.section {
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

.outline-item {
  padding: 16px;
  background: #FAFAFA;
  border-radius: 8px;
  margin-bottom: 12px;
}

.item-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.chapter-num {
  font-size: 13px;
  font-weight: 500;
  color: #6B7B8D;
  min-width: 60px;
}

.title-input {
  flex: 1;
}

.character-card {
  padding: 20px;
  background: #FAFAFA;
  border-radius: 8px;
  margin-bottom: 16px;
}

.char-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.name-input {
  width: 150px;
}

.role-select {
  width: 100px;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
}
</style>