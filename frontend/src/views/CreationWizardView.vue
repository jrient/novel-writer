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
        <el-step title="创作思路" description="描述故事构思" />
        <el-step title="生成地图" description="AI 生成场景地图" />
        <el-step title="生成部分" description="划分故事部分" />
        <el-step title="生成角色" description="创建角色库" />
        <el-step title="添加笔记" description="伏笔与灵感" />
        <el-step title="确认创建" description="开始创作" />
      </el-steps>
    </div>

    <!-- 步骤内容 -->
    <main class="page-main">
      <transition name="fade" mode="out-in">
        <StepOneIdea v-if="wizardStore.currentStep === 1" />
        <StepTwoMaps v-else-if="wizardStore.currentStep === 2" />
        <StepThreeParts v-else-if="wizardStore.currentStep === 3" />
        <StepFourCharacters v-else-if="wizardStore.currentStep === 4" />
        <StepFiveNotes v-else-if="wizardStore.currentStep === 5" />
        <StepSixConfirm v-else-if="wizardStore.currentStep === 6" />
        <StepSevenComplete v-else-if="wizardStore.currentStep === 7" />
      </transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useWizardStore } from '@/stores/wizard'
// 新的向导步骤组件
import StepOneIdea from '@/components/wizard/StepOneIdea.vue'
import StepTwoMaps from '@/components/wizard/StepTwoMaps.vue'
import StepThreeParts from '@/components/wizard/StepThreeParts.vue'
import StepFourCharacters from '@/components/wizard/StepFourCharacters.vue'
import StepFiveNotes from '@/components/wizard/StepFiveNotes.vue'
import StepSixConfirm from '@/components/wizard/StepSixConfirm.vue'
import StepSevenComplete from '@/components/wizard/StepSevenComplete.vue'

const router = useRouter()
const wizardStore = useWizardStore()

onMounted(async () => {
  // 尝试加载草稿
  const hasDraft = wizardStore.loadDraft()
  if (hasDraft && wizardStore.currentStep > 1) {
    try {
      await ElMessageBox.confirm(
        '检测到上次未完成的创作进度，是否继续？',
        '恢复进度',
        {
          confirmButtonText: '继续',
          cancelButtonText: '重新开始',
          type: 'info',
        }
      )
      // 用户选择继续，草稿已加载
    } catch {
      // 用户选择重新开始
      wizardStore.reset()
    }
  }
})

onUnmounted(() => {
  // 离开页面时如果还没完成，保存草稿
  if (wizardStore.currentStep < 7 && wizardStore.currentStep > 1) {
    wizardStore.saveDraft()
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
  max-width: 900px;
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
  font-size: 13px;
}

:deep(.el-step__description) {
  font-size: 11px;
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

  :deep(.el-step__description) {
    display: none;
  }
}
</style>