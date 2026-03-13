<template>
  <div class="step-one">
    <div class="step-header">
      <h2>开始你的创作之旅</h2>
      <p class="step-desc">告诉我们你的故事构思，AI 将为你生成地图大纲和角色设定</p>
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
              <el-option label="修仙" value="修仙" />
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
          :rows="6"
          placeholder="描述你的故事构思，包括：
- 故事背景和世界观设定
- 主角是谁，有什么特点
- 核心冲突是什么
- 你希望故事走向
- 有哪些主要场景（如：青云宗、北境荒漠等）

例如：一个普通的渔村少年，偶然发现父亲留下的星际通行证，从此踏上寻找父亲的星际冒险之旅。故事发生在星际联邦时代，主要场景包括渔村、星际港口、星际学院等..."
          maxlength="2000"
          show-word-limit
        />
      </el-form-item>

      <div class="tips-box">
        <h4>💡 提示</h4>
        <ul>
          <li>不需要提前规划章节数和字数，AI 会根据你的构思自动生成合适的大纲结构</li>
          <li>可以描述你想要的场景（地图），AI 会为每个场景生成详细的部分和章节</li>
          <li>角色可以在多个场景中复用，AI 会帮你管理角色库</li>
        </ul>
      </div>
    </el-form>

    <div class="step-actions">
      <el-button type="primary" size="large" @click="handleNext" :disabled="!canProceed">
        下一步：生成地图
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

.tips-box {
  background: rgba(107, 123, 141, 0.05);
  border-radius: 8px;
  padding: 16px;
  margin-top: 16px;
}

.tips-box h4 {
  font-size: 14px;
  font-weight: 500;
  color: #6B7B8D;
  margin: 0 0 8px;
}

.tips-box ul {
  margin: 0;
  padding-left: 20px;
}

.tips-box li {
  font-size: 13px;
  color: #7A7A7A;
  line-height: 1.8;
}

.step-actions {
  display: flex;
  justify-content: center;
  margin-top: 32px;
}
</style>