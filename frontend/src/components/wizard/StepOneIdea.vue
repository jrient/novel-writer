<template>
  <div class="step-one">
    <div class="step-header">
      <h2>开始你的创作之旅</h2>
      <p class="step-desc">告诉我们你的故事构思，AI 将为你生成完整的大纲和角色设定</p>
    </div>

    <el-form
      ref="formRef"
      :model="wizardStore.ideaData"
      :rules="rules"
      label-position="top"
      class="idea-form"
    >
      <el-row :gutter="24">
        <el-col :span="12">
          <el-form-item label="小说标题" prop="title">
            <el-input
              v-model="wizardStore.ideaData.title"
              placeholder="给你的小说起个名字"
              maxlength="50"
              show-word-limit
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="小说类型" prop="genre">
            <el-select v-model="wizardStore.ideaData.genre" placeholder="选择类型" style="width: 100%">
              <el-option label="奇幻" value="奇幻" />
              <el-option label="科幻" value="科幻" />
              <el-option label="玄幻" value="玄幻" />
              <el-option label="言情" value="言情" />
              <el-option label="悬疑" value="悬疑" />
              <el-option label="历史" value="历史" />
              <el-option label="武侠" value="武侠" />
              <el-option label="都市" value="都市" />
              <el-option label="恐怖" value="恐怖" />
              <el-option label="军事" value="军事" />
              <el-option label="其他" value="其他" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="故事简介" prop="description">
        <el-input
          v-model="wizardStore.ideaData.description"
          type="textarea"
          :rows="5"
          placeholder="描述你的故事构思，包括：
- 故事背景和世界观设定
- 主角是谁，有什么特点
- 核心冲突是什么
- 你希望故事走向

例如：一个普通的渔村少年，偶然发现父亲留下的星际通行证，从此踏上寻找父亲的星际冒险之旅..."
          maxlength="1000"
          show-word-limit
        />
      </el-form-item>

      <el-row :gutter="24">
        <el-col :span="12">
          <el-form-item label="目标字数">
            <el-input-number
              v-model="wizardStore.ideaData.target_word_count"
              :min="10000"
              :max="5000000"
              :step="10000"
              style="width: 100%"
            />
            <div class="field-hint">
              <span :class="novelSizeClass">{{ novelSizeLabel }}</span>
              · 短篇 3-10 万 · 中篇 10-30 万 · 长篇 30 万+
            </div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="计划章节数">
            <el-input-number
              v-model="wizardStore.ideaData.chapter_count"
              :min="1"
              :max="100"
              style="width: 100%"
            />
            <div class="field-hint">
              <span class="words-highlight">每章约 {{ averageWordsPerChapter }} 字</span>
              <span v-if="wordsPerChapterHint" class="words-hint">{{ wordsPerChapterHint }}</span>
            </div>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="step-actions">
      <el-button type="primary" size="large" @click="handleNext" :disabled="!canProceed">
        下一步：生成大纲
        <el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useWizardStore } from '@/stores/wizard'

const wizardStore = useWizardStore()
const formRef = ref<FormInstance>()

const rules: FormRules = {
  title: [{ required: true, message: '请输入小说标题', trigger: 'blur' }],
  description: [{ required: true, message: '请描述你的故事构思', trigger: 'blur' }],
}

const averageWordsPerChapter = computed(() => {
  const count = Math.round(wizardStore.ideaData.target_word_count / wizardStore.ideaData.chapter_count)
  if (count >= 10000) {
    return (count / 10000).toFixed(1) + ' 万'
  }
  return count.toLocaleString()
})

const novelSizeLabel = computed(() => {
  const words = wizardStore.ideaData.target_word_count
  if (words < 100000) return '短篇小说'
  if (words < 300000) return '中篇小说'
  return '长篇小说'
})

const novelSizeClass = computed(() => {
  const words = wizardStore.ideaData.target_word_count
  if (words < 100000) return 'size-short'
  if (words < 300000) return 'size-medium'
  return 'size-long'
})

const wordsPerChapterHint = computed(() => {
  const count = Math.round(wizardStore.ideaData.target_word_count / wizardStore.ideaData.chapter_count)
  if (count < 2000) return '（偏短，建议增加字数或减少章节）'
  if (count > 10000) return '（偏长，建议增加章节数）'
  return ''
})

const canProceed = computed(() => {
  return wizardStore.ideaData.title.trim() && wizardStore.ideaData.description.trim()
})

async function handleNext() {
  if (!formRef.value) return
  await formRef.value.validate((valid) => {
    if (valid) {
      wizardStore.nextStep()
    }
  })
}
</script>

<style scoped>
.step-one {
  max-width: 800px;
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

.idea-form {
  background: white;
  padding: 32px;
  border-radius: 14px;
  border: 1px solid #E0DFDC;
}

.field-hint {
  font-size: 12px;
  color: #9E9E9E;
  margin-top: 4px;
}

.size-short {
  color: #67C23A;
  font-weight: 500;
}

.size-medium {
  color: #E6A23C;
  font-weight: 500;
}

.size-long {
  color: #F56C6C;
  font-weight: 500;
}

.words-highlight {
  color: #6B7B8D;
  font-weight: 500;
}

.words-hint {
  color: #E6A23C;
  margin-left: 8px;
}

.step-actions {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}
</style>