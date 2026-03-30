<template>
  <div class="wizard-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="logo-area" @click="router.push('/drama')">
          <span class="logo-icon">&#127916;</span>
          <h1 class="logo">AI 剧本引导</h1>
        </div>
        <div class="header-right">
          <span v-if="dramaStore.currentProject" class="project-title-tag">
            {{ dramaStore.currentProject.title }}
          </span>
          <el-button text @click="router.push('/drama')">
            <el-icon><ArrowLeft /></el-icon> 返回列表
          </el-button>
        </div>
      </div>
    </header>

    <!-- Steps bar -->
    <div class="steps-bar">
      <div
        v-for="(step, i) in wizardSteps"
        :key="i"
        class="step-item"
        :class="{ active: i === wizardStepIndex, done: i < wizardStepIndex }"
      >
        <span class="step-dot">{{ i < wizardStepIndex ? '&#10003;' : i + 1 }}</span>
        <span class="step-label">{{ step.title }}</span>
        <span v-if="i < wizardSteps.length - 1" class="step-line" />
      </div>
    </div>

    <!-- Main content -->
    <div class="wizard-main">

      <!-- Step 0: AI 问答 -->
      <template v-if="wizardStepIndex === 0">
        <div class="chat-container">
          <WizardChat
            v-if="!pageLoading"
            :project-id="projectId"
            :session="dramaStore.session"
            @outline-ready="handleOutlineReady"
            @questions-complete="handleQuestionsComplete"
          />
          <div v-else class="loading-area">
            <el-skeleton :rows="5" animated />
          </div>
        </div>

        <div class="wizard-footer">
          <span v-if="questionCount < 5" class="hint-text">
            还需回答 {{ 5 - questionCount }} 个问题才能继续
          </span>
          <el-button
            v-else
            type="primary"
            size="large"
            :loading="summarizing"
            @click="handleNextStep"
            round
          >
            下一步
          </el-button>
        </div>
      </template>

      <!-- Step 1: 信息确认 -->
      <template v-else-if="wizardStepIndex === 1">
        <div class="summary-review">
          <div class="summary-header">
            <h3>创作信息汇总</h3>
            <p>请检查 AI 汇总的信息，确认后开始生成大纲</p>
          </div>

          <div class="summary-card">
            <div class="summary-section">
              <h4>故事概要</h4>
              <p>{{ sessionSummary?.故事概要 }}</p>
            </div>

            <div class="summary-section">
              <h4>主要角色</h4>
              <ul>
                <li v-for="c in sessionSummary?.主要角色" :key="c">{{ c }}</li>
              </ul>
            </div>

            <div class="summary-section">
              <h4>核心冲突</h4>
              <p>{{ sessionSummary?.核心冲突 }}</p>
            </div>

            <div class="summary-section">
              <h4>场景设定</h4>
              <p>{{ sessionSummary?.场景设定 }}</p>
            </div>

            <div class="summary-section">
              <h4>风格基调</h4>
              <p>{{ sessionSummary?.风格基调 }}</p>
            </div>
          </div>

          <div class="summary-actions">
            <el-button @click="handleBackToChat">重新问答</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="generatingOutline"
              @click="handleGenerateOutline"
              round
            >
              生成大纲
            </el-button>
          </div>
        </div>
      </template>

      <!-- Step 2: 大纲预览 -->
      <template v-else-if="wizardStepIndex === 2">
        <div class="outline-review">
          <div class="outline-header">
            <h3 class="outline-title">剧本大纲</h3>
            <p class="outline-subtitle">请检查 AI 生成的大纲，可以在下方编辑后确认</p>
          </div>

          <div class="outline-tree-wrapper">
            <ScriptOutlineTree
              :nodes="outlineDraftNodes"
              :script-type="dramaStore.currentProject?.script_type || 'dynamic'"
              :current-node-id="null"
              @select-node="() => {}"
              @add-node="() => {}"
              @delete-node="() => {}"
              @rename-node="() => {}"
            />
          </div>

          <div class="outline-actions">
            <el-button @click="wizardStepIndex = 1">返回确认</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="confirming"
              @click="handleConfirmOutline"
              round
            >
              确认大纲，开始创作
            </el-button>
          </div>
        </div>
      </template>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useDramaStore } from '@/stores/drama'
import { summarizeSession, streamGenerateOutline } from '@/api/drama'
import type { SessionSummary } from '@/api/drama'
import WizardChat from '@/components/drama/WizardChat.vue'
import ScriptOutlineTree from '@/components/drama/ScriptOutlineTree.vue'

const route = useRoute()
const router = useRouter()
const dramaStore = useDramaStore()

const projectId = computed(() => Number(route.params.id))
const pageLoading = ref(true)
const confirming = ref(false)
const wizardStepIndex = ref(0)
const questionCount = ref(0)
const summarizing = ref(false)
const sessionSummary = ref<SessionSummary | null>(null)
const generatingOutline = ref(false)
const wizardSteps = [
  { title: 'AI 问答' },
  { title: '信息确认' },
  { title: '大纲预览' },
  { title: '开始创作' },
]

// Convert outline_draft sections to display nodes for review step
const outlineDraftNodes = computed(() => {
  const session = dramaStore.session
  if (!session?.outline_draft?.sections) return dramaStore.nodes

  let idCounter = 1
  function convertSections(sections: any[], parentId: number | null): any[] {
    return sections.map((section, index) => {
      const nodeId = idCounter++
      const node: any = {
        id: nodeId,
        project_id: projectId.value,
        parent_id: parentId,
        node_type: section.node_type || 'section',
        title: section.title,
        content: section.content,
        speaker: section.speaker,
        visual_desc: section.visual_desc,
        sort_order: index,
        is_completed: false,
        metadata_: null,
        created_at: '',
        updated_at: null,
        children: section.children ? convertSections(section.children, nodeId) : [],
      }
      return node
    })
  }
  return convertSections(session.outline_draft.sections as any[], null)
})

async function handleOutlineReady() {
  // Outline draft saved in session, reload and move to review step
  try {
    await dramaStore.fetchSession(projectId.value)
    wizardStepIndex.value = 2
  } catch {
    ElMessage.error('加载大纲失败')
  }
}

function handleQuestionsComplete() {
  // 子组件通知问答完成
  questionCount.value = 5
}

async function handleNextStep() {
  summarizing.value = true
  try {
    const summary = await summarizeSession(projectId.value)
    sessionSummary.value = summary
    wizardStepIndex.value = 1
  } catch {
    ElMessage.error('汇总信息失败')
  } finally {
    summarizing.value = false
  }
}

function handleBackToChat() {
  sessionSummary.value = null
  wizardStepIndex.value = 0
}

async function handleGenerateOutline() {
  generatingOutline.value = true
  try {
    // 流式生成大纲
    streamGenerateOutline(
      projectId.value,
      () => {
        // 流式输出 chunk（忽略）
      },
      async (outline) => {
        generatingOutline.value = false
        if (outline) {
          await dramaStore.fetchSession(projectId.value)
          wizardStepIndex.value = 2
        } else {
          ElMessage.warning('大纲生成中，请稍后刷新')
        }
      },
      (error) => {
        generatingOutline.value = false
        ElMessage.error('生成大纲失败：' + error)
      },
    )
  } catch {
    generatingOutline.value = false
    ElMessage.error('生成大纲失败')
  }
}


async function handleConfirmOutline() {
  confirming.value = true
  try {
    await dramaStore.confirmProjectOutline(projectId.value)
    ElMessage.success('大纲已确认！正在跳转工作台...')
    setTimeout(() => {
      router.push(`/drama/workbench/${projectId.value}`)
    }, 800)
  } catch {
    ElMessage.error('确认失败，请重试')
  } finally {
    confirming.value = false
  }
}

onMounted(async () => {
  pageLoading.value = true
  try {
    await Promise.all([
      dramaStore.fetchProject(projectId.value),
      dramaStore.fetchSession(projectId.value),
      dramaStore.fetchNodes(projectId.value),
    ])

    // If nodes already exist, skip to outline review
    if (dramaStore.nodes.length && dramaStore.currentProject?.status !== 'drafting') {
      wizardStepIndex.value = 2
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    pageLoading.value = false
  }
})
</script>

<style scoped>
.wizard-page {
  min-height: 100vh;
  background-color: #F0EFEC;
  display: flex;
  flex-direction: column;
}

.page-header {
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
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

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.logo-icon { font-size: 22px; }

.logo {
  font-size: 20px;
  font-weight: 700;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  font-family: 'Noto Serif SC', serif;
  margin: 0;
}

.project-title-tag {
  font-size: 13px;
  color: #7A7A7A;
  background: #F0EFEC;
  padding: 4px 12px;
  border-radius: 12px;
  border: 1px solid #E0DFDC;
}

.steps-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px 32px 0;
  flex-shrink: 0;
}

.wizard-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  max-width: 1200px;
  width: 100%;
  margin: 0 auto;
  padding: 24px 32px 0;
  min-height: 0;
}

.chat-container {
  flex: 1;
  background: white;
  border-radius: 16px;
  border: 1px solid #E0DFDC;
  overflow: hidden;
  min-height: 480px;
  display: flex;
  flex-direction: column;
}

.loading-area {
  padding: 32px;
  flex: 1;
}

.wizard-footer {
  padding: 16px 0;
  text-align: center;
  flex-shrink: 0;
}

.hint-text {
  font-size: 14px;
  color: #9E9E9E;
}

/* 信息确认页 */
.summary-review {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 32px;
}

.summary-header {
  text-align: center;
}

.summary-header h3 {
  font-size: 22px;
  font-weight: 700;
  color: #2C2C2C;
  margin: 0 0 6px;
  font-family: 'Noto Serif SC', serif;
}

.summary-header p {
  font-size: 13px;
  color: #7A7A7A;
  margin: 0;
}

.summary-card {
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 16px;
  padding: 24px;
}

.summary-section {
  margin-bottom: 16px;
}

.summary-section:last-child {
  margin-bottom: 0;
}

.summary-section h4 {
  font-size: 14px;
  font-weight: 600;
  color: #6B7B8D;
  margin: 0 0 8px;
}

.summary-section p,
.summary-section ul {
  font-size: 15px;
  color: #2C2C2C;
  margin: 0;
  line-height: 1.6;
}

.summary-section ul {
  padding-left: 20px;
}

.summary-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

/* Outline review */
.outline-review {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding-bottom: 32px;
}

.outline-header {
  text-align: center;
}

.outline-title {
  font-size: 22px;
  font-weight: 700;
  color: #2C2C2C;
  margin: 0 0 6px;
  font-family: 'Noto Serif SC', serif;
}

.outline-subtitle {
  font-size: 13px;
  color: #7A7A7A;
  margin: 0;
}

.outline-tree-wrapper {
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 16px;
  overflow: hidden;
  min-height: 300px;
  max-height: 480px;
}

.outline-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

/* Steps bar */
.steps-bar {
  display: flex;
  align-items: center;
  max-width: 600px;
  margin: 0 auto;
  padding: 20px 32px 0;
}

.step-item {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
}

.step-item:last-child {
  flex: 0 0 auto;
}

.step-dot {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid #D0D0D0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: #B0B0B0;
  background: white;
  flex-shrink: 0;
  transition: all 0.3s;
}

.step-label {
  margin-left: 8px;
  font-size: 14px;
  color: #999;
  white-space: nowrap;
  flex-shrink: 0;
  transition: color 0.3s;
}

.step-line {
  flex: 1;
  height: 1px;
  background: #D0D0D0;
  margin: 0 12px;
  min-width: 20px;
  transition: background 0.3s;
}

.step-item.active .step-dot {
  border-color: #6B7B8D;
  color: #6B7B8D;
  box-shadow: 0 0 0 3px rgba(107, 123, 141, 0.15);
}

.step-item.active .step-label {
  color: #2C2C2C;
  font-weight: 600;
}

.step-item.done .step-dot {
  border-color: #6B7B8D;
  background: #6B7B8D;
  color: white;
}

.step-item.done .step-label {
  color: #6B7B8D;
}

.step-item.done .step-line {
  background: #6B7B8D;
}

@media (max-width: 768px) {
  .wizard-main { padding: 16px; }
  .steps-bar { padding: 16px 16px 0; }
  .page-header { padding: 0 16px; }
  .step-dot { width: 24px; height: 24px; font-size: 12px; }
  .step-label { font-size: 13px; }
}
</style>
