<template>
  <div class="wizard-page">
    <!-- 顶部导航栏 -->
    <header class="page-header">
      <div class="header-content">
        <div class="logo-area" @click="goHome">
          <span class="logo-icon">&#9997;</span>
          <h1 class="logo">AI小说创作平台</h1>
        </div>
        <el-button text @click="goHome">
          <el-icon><ArrowLeft /></el-icon> 返回首页
        </el-button>
      </div>
    </header>

    <!-- 步骤指示器 -->
    <div class="steps-container">
      <el-steps :active="wizardStore.currentStep - 1" align-center>
        <el-step title="创作思路" description="描述你的故事构思" />
        <el-step title="AI 生成" description="生成大纲和角色" />
        <el-step title="确认风格" description="选择参考小说" />
        <el-step title="完成" description="开始创作" />
      </el-steps>
    </div>

    <!-- 步骤内容 -->
    <main class="page-main">
      <transition name="fade" mode="out-in">
        <StepOneIdea v-if="wizardStore.currentStep === 1" />
        <StepTwoGenerate v-else-if="wizardStore.currentStep === 2" />
        <StepThreeConfirm v-else-if="wizardStore.currentStep === 3" />
        <StepFourComplete v-else-if="wizardStore.currentStep === 4" />
      </transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { useWizardStore } from '@/stores/wizard'
import StepOneIdea from '@/components/wizard/StepOneIdea.vue'
import StepTwoGenerate from '@/components/wizard/StepTwoGenerate.vue'
import StepThreeConfirm from '@/components/wizard/StepThreeConfirm.vue'
import StepFourComplete from '@/components/wizard/StepFourComplete.vue'

const router = useRouter()
const wizardStore = useWizardStore()

onMounted(() => {
  // 每次进入向导页面重置状态
  wizardStore.reset()
})

onUnmounted(() => {
  // 离开页面时如果还没完成，清理状态
  if (wizardStore.currentStep < 4) {
    wizardStore.reset()
  }
})

function goHome() {
  router.push('/projects')
}
</script>

<style scoped>
.wizard-page {
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
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
}

.logo-icon {
  font-size: 24px;
}

.logo {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
}

.steps-container {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px 32px 0;
}

.page-main {
  max-width: 1200px;
  margin: 0 auto;
  padding: 32px;
}

/* 过渡动画 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* 覆盖 Element Plus 步骤样式 */
:deep(.el-step__title) {
  font-size: 14px;
}

:deep(.el-step__description) {
  font-size: 12px;
}

:deep(.el-step.is-process .el-step__title) {
  color: #6B7B8D;
}

:deep(.el-step.is-process .el-step__icon) {
  border-color: #6B7B8D;
  color: #6B7B8D;
}

:deep(.el-step.is-finish .el-step__title) {
  color: #6B7B8D;
}

:deep(.el-step.is-finish .el-step__icon) {
  border-color: #6B7B8D;
  color: #6B7B8D;
}

@media (max-width: 768px) {
  .page-header {
    padding: 0 16px;
  }

  .steps-container {
    padding: 24px 16px 0;
  }

  .page-main {
    padding: 16px;
  }
}
</style>