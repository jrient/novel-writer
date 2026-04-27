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
            :concept="dramaStore.currentProject?.concept"
            @outline-ready="handleOutlineReady"
            @questions-complete="handleQuestionsComplete"
            @question-answered="(count: number) => questionCount = count"
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
              <h4>故事概要 <span class="field-hint">（AI 内部凝练版，1-2 句）</span></h4>
              <el-input
                v-model="editableSummary.故事概要"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="一句话描述核心剧情"
              />
            </div>

            <div class="summary-section">
              <h4>
                故事简介
                <span class="field-hint">（面向读者，3-5 段 500-800 字，可作宣传文案）</span>
                <span class="field-counter">{{ (editableSummary.故事简介 || '').length }} 字</span>
              </h4>
              <el-input
                v-model="editableSummary.故事简介"
                type="textarea"
                :autosize="{ minRows: 6, maxRows: 15 }"
                placeholder="例：他是江湖上人人闻风丧胆的杀手，却在一个雨夜救下了濒死的少女……"
              />
            </div>

            <div class="summary-section">
              <div class="bios-header">
                <h4>主要人物小传 <span class="field-hint">（中版结构化，每人 5 字段）</span></h4>
                <el-button text size="small" @click="addCharacterBio">+ 添加人物</el-button>
              </div>
              <div v-if="!(editableSummary.人物小传 && editableSummary.人物小传.length)" class="bios-empty">
                暂无人物小传，点击右上"+ 添加人物"开始填写
              </div>
              <div
                v-for="(bio, i) in editableSummary.人物小传 || []"
                :key="i"
                class="bio-card"
              >
                <div class="bio-card-header">
                  <el-input v-model="bio.姓名" placeholder="姓名" class="bio-name" />
                  <el-button text type="danger" size="small" @click="removeCharacterBio(i)">删除</el-button>
                </div>
                <el-input v-model="bio.身份" placeholder="身份：年龄/职业/社会角色（50字内）" size="small" />
                <el-input v-model="bio.目标" placeholder="目标：表面目标 + 内心渴望（50字内）" size="small" />
                <el-input v-model="bio.弱点" placeholder="弱点：致命弱点/恐惧/盲点（50字内）" size="small" />
                <el-input v-model="bio.关键关系" placeholder="关键关系：与其他主角的关系（50字内）" size="small" />
                <el-input v-model="bio.典型台词" placeholder="典型台词：一句能体现性格的台词（30字内）" size="small" />
              </div>
            </div>

            <div class="summary-section">
              <h4>主要角色 <span class="field-hint">（由人物小传自动同步，AI 大纲生成消费）</span></h4>
              <div v-if="editableSummary.主要角色.length" class="role-tags">
                <el-tag
                  v-for="(role, i) in editableSummary.主要角色"
                  :key="i"
                  type="info"
                  size="large"
                  class="role-tag"
                >
                  {{ role }}
                </el-tag>
              </div>
              <div v-else class="bios-empty">
                请在"主要人物小传"中添加人物
              </div>
            </div>

            <div class="summary-section">
              <h4>核心冲突</h4>
              <el-input
                v-model="editableSummary.核心冲突"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="核心冲突描述"
              />
            </div>

            <div class="summary-section">
              <h4>主角弱点</h4>
              <el-input
                v-model="editableSummary.主角弱点"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 3 }"
                placeholder="主角的致命弱点/恐惧/软肋，让读者产生代入感。例：他很强，但他害怕失去仅存的家人……"
              />
            </div>

            <div class="summary-section">
              <h4>反派逻辑</h4>
              <el-input
                v-model="editableSummary.反派逻辑"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 3 }"
                placeholder="反派为什么觉得自己是对的，不是纯坏。例：他认为优胜劣汰是自然法则，弱肉强食天经地义……"
              />
            </div>

            <div class="summary-section">
              <h4>开局钩子</h4>
              <el-input
                v-model="editableSummary.开局钩子"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 3 }"
                placeholder="第一集的悬念/反转/迫在眉睫的损失，吸引读者继续看。例：故事从一场意外开始，主角发现自己被陷害，必须在24小时内找到证据……"
              />
            </div>

            <div class="summary-section">
              <h4>场景设定</h4>
              <el-input
                v-model="editableSummary.场景设定"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="主要场景设定"
              />
            </div>

            <div class="summary-section">
              <h4>风格基调</h4>
              <el-input
                v-model="editableSummary.风格基调"
                placeholder="风格基调（如悬疑、温情、喜剧等）"
              />
            </div>

            <div class="summary-section">
              <h4>目标集数</h4>
              <p class="summary-hint">AI 将生成这么多集的简要大纲，之后可逐集展开详细场景</p>
              <el-input-number
                v-model="editableSummary.目标集数"
                :min="1"
                :max="200"
                :step="10"
                controls-position="right"
                style="width: 160px"
              />
            </div>
          </div>

          <div class="summary-actions">
            <el-button @click="handleBackToChat">重新问答</el-button>
            <el-button @click="copyProfileMarkdown">复制档案 Markdown</el-button>
            <el-button @click="downloadProfileMarkdown">下载档案 .md</el-button>
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
            <p class="outline-subtitle">
              共 {{ outlineSections.length }} 集 · 可逐集生成或一键生成全部内容
            </p>
          </div>

          <div class="outline-tree-wrapper">
            <OutlineDraftPreview
              :project-id="projectId"
              :sections="outlineSections"
              :disable-individual="isExpandingAll"
              @episode-expanded="handleEpisodeExpanded"
              @expanding-change="isSingleExpanding = $event"
            />
          </div>

          <div class="outline-actions">
            <el-button @click="wizardStepIndex = 1">返回确认</el-button>
            <el-button
              plain
              type="warning"
              :loading="regeneratingOutline"
              @click="handleRegenerateOutline"
            >
              {{ regeneratingOutline ? '重新生成中...' : '重新生成大纲' }}
            </el-button>
            <el-button
              plain
              :loading="isExpandingAll"
              :disabled="allExpanded"
              @click="handleExpandAll"
            >
              {{ isExpandingAll ? `生成中 (${expandAllCurrent}/${expandAllTotal})` : allExpanded ? '已全部生成' : '生成全部内容' }}
            </el-button>
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
import { ref, reactive, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDramaStore } from '@/stores/drama'
import { summarizeSession, updateSessionSummary, streamGenerateOutline, streamExpandEpisode } from '@/api/drama'
import type { SessionSummary } from '@/api/drama'
import WizardChat from '@/components/drama/WizardChat.vue'
import OutlineDraftPreview from '@/components/drama/OutlineDraftPreview.vue'

const route = useRoute()
const router = useRouter()
const dramaStore = useDramaStore()

const projectId = computed(() => Number(route.params.id))
const pageLoading = ref(true)
const confirming = ref(false)

// 一键展开全部场景
const isExpandingAll = ref(false)
const expandAllCurrent = ref(0)
const expandAllTotal = ref(0)
const isSingleExpanding = ref(false)
const currentAbortController = ref<AbortController | null>(null)

const wizardStepIndex = ref(Number(route.query.step) || 0)
const questionCount = ref(0)
const summarizing = ref(false)
const sessionSummary = ref<SessionSummary | null>(null)
const editableSummary = reactive<SessionSummary>({
  故事概要: '',
  主要角色: [],
  核心冲突: '',
  主角弱点: '',
  反派逻辑: '',
  开局钩子: '',
  故事简介: '',
  人物小传: [],
  场景设定: '',
  风格基调: '',
  目标集数: 20,
})
const generatingOutline = ref(false)
const regeneratingOutline = ref(false)
const wizardSteps = [
  { title: 'AI 问答' },
  { title: '信息确认' },
  { title: '大纲预览' },
  { title: '开始创作' },
]

// Sync step to URL query param
watch(wizardStepIndex, (step) => {
  const currentStep = Number(route.query.step) || 0
  if (currentStep !== step) {
    router.replace({ query: { ...route.query, step: String(step) } })
  }
})

const outlineSections = computed(() => {
  const draft = dramaStore.session?.outline_draft
  if (!draft?.sections) return []
  return draft.sections as Array<{
    node_type: string
    title: string
    content: string
    sort_order: number
    generated?: boolean
    children?: Array<{ node_type: string; title: string; content: string; sort_order: number }>
  }>
})

const allExpanded = computed(() =>
  outlineSections.value.length > 0 &&
  outlineSections.value.every(ep => ep.generated === true)
)

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

function syncEditableSummary(summary: SessionSummary) {
  editableSummary.故事概要 = summary.故事概要 || ''
  editableSummary.主要角色 = [...(summary.主要角色 || [])]
  editableSummary.核心冲突 = summary.核心冲突 || ''
  editableSummary.主角弱点 = summary.主角弱点 || ''
  editableSummary.反派逻辑 = summary.反派逻辑 || ''
  editableSummary.开局钩子 = summary.开局钩子 || ''
  editableSummary.故事简介 = summary.故事简介 || ''
  editableSummary.人物小传 = (summary.人物小传 || []).map(b => ({
    姓名: b.姓名 || '',
    身份: b.身份 || '',
    目标: b.目标 || '',
    弱点: b.弱点 || '',
    关键关系: b.关键关系 || '',
    典型台词: b.典型台词 || '',
  }))
  editableSummary.场景设定 = summary.场景设定 || ''
  editableSummary.风格基调 = summary.风格基调 || ''
  editableSummary.目标集数 = summary.目标集数 ?? 20
}

function addCharacterBio() {
  if (!editableSummary.人物小传) editableSummary.人物小传 = []
  editableSummary.人物小传.push({
    姓名: '',
    身份: '',
    目标: '',
    弱点: '',
    关键关系: '',
    典型台词: '',
  })
}

function removeCharacterBio(idx: number) {
  editableSummary.人物小传?.splice(idx, 1)
}

// 自动同步：人物小传 → 主要角色（单向，人物小传是 source of truth）
// 注意：人物小传为空时不重置主要角色，避免老 session（仅有主要角色字符串列表）被清空
watch(
  () => editableSummary.人物小传,
  (bios) => {
    if (!bios || !bios.length) return
    editableSummary.主要角色 = bios
      .filter(b => b.姓名.trim())
      .map(b => (b.身份.trim() ? `${b.姓名.trim()}：${b.身份.trim()}` : b.姓名.trim()))
  },
  { deep: true },
)

function buildProfileMarkdown(): string {
  const s = editableSummary
  const title = dramaStore.currentProject?.title || '剧本档案'
  const lines: string[] = [`# ${title}`, '']
  if (s.故事简介) {
    lines.push('## 故事简介', '', s.故事简介, '')
  }
  if (s.人物小传 && s.人物小传.length) {
    lines.push('## 主要人物小传', '')
    for (const c of s.人物小传) {
      if (!c.姓名.trim()) continue
      lines.push(`### ${c.姓名}`, '')
      if (c.身份) lines.push(`- **身份**：${c.身份}`)
      if (c.目标) lines.push(`- **目标**：${c.目标}`)
      if (c.弱点) lines.push(`- **弱点**：${c.弱点}`)
      if (c.关键关系) lines.push(`- **关键关系**：${c.关键关系}`)
      if (c.典型台词) lines.push(`- **典型台词**：${c.典型台词}`)
      lines.push('')
    }
  }
  return lines.join('\n')
}

async function copyProfileMarkdown() {
  const md = buildProfileMarkdown()
  if (!md.trim() || md.trim().split('\n').length <= 1) {
    ElMessage.warning('档案内容为空')
    return
  }
  try {
    await navigator.clipboard.writeText(md)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请检查浏览器剪贴板权限')
  }
}

function downloadProfileMarkdown() {
  const md = buildProfileMarkdown()
  if (!md.trim() || md.trim().split('\n').length <= 1) {
    ElMessage.warning('档案内容为空')
    return
  }
  const title = dramaStore.currentProject?.title || '剧本档案'
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${title}-档案.md`
  a.click()
  URL.revokeObjectURL(a.href)
}

async function handleNextStep() {
  summarizing.value = true
  try {
    const summary = await summarizeSession(projectId.value)
    sessionSummary.value = summary
    syncEditableSummary(summary)
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
    // Save edited summary before generating
    await updateSessionSummary(projectId.value, { ...editableSummary })
    // 流式生成大纲
    streamGenerateOutline(
      projectId.value,
      () => {
        // 流式输出 chunk（忽略）
      },
      async () => {
        generatingOutline.value = false
        await dramaStore.fetchSession(projectId.value)
        if (dramaStore.session?.outline_draft) {
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

async function handleRegenerateOutline() {
  try {
    await ElMessageBox.confirm(
      '重新生成将覆盖当前大纲，已生成的内容将被清除。确定要重新生成吗？',
      '重新生成大纲',
      {
        confirmButtonText: '确定重新生成',
        cancelButtonText: '取消',
        type: 'warning',
      },
    )
  } catch {
    return
  }

  regeneratingOutline.value = true
  try {
    streamGenerateOutline(
      projectId.value,
      () => {},
      async () => {
        regeneratingOutline.value = false
        await dramaStore.fetchSession(projectId.value)
        ElMessage.success('大纲已重新生成')
      },
      (error) => {
        regeneratingOutline.value = false
        ElMessage.error('重新生成失败：' + error)
      },
    )
  } catch {
    regeneratingOutline.value = false
    ElMessage.error('重新生成失败')
  }
}


async function handleEpisodeExpanded(_index: number) {
  // 刷新 session 以获取最新的 outline_draft（含已生成内容的标记）
  await dramaStore.fetchSession(projectId.value)
}

async function handleExpandAll() {
  // 防止重复触发
  if (isExpandingAll.value) {
    ElMessage.warning('正在生成全部内容，请等待完成')
    return
  }
  // 单集正在展开中，拒绝
  if (isSingleExpanding.value) {
    ElMessage.warning('请等待当前集生成完成')
    return
  }

  const sections = outlineSections.value
  let targets: Array<{ originalIndex: number }>

  // 检查是否有已生成的集
  const hasExpanded = sections.some(ep => ep.generated === true)

  if (hasExpanded) {
    try {
      await ElMessageBox.confirm(
        '部分集已生成，请选择处理方式',
        '生成全部内容',
        {
          distinguishCancelAndClose: true,
          confirmButtonText: '全部重新生成',
          cancelButtonText: '跳过已生成',
        },
      )
      // 用户点"全部重新展开" (confirm)
      targets = sections.map((_, i) => ({ originalIndex: i }))
    } catch (action) {
      if (action === 'cancel') {
        // 用户点"跳过已展开"
        targets = sections
          .map((ep, i) => ({ ep, originalIndex: i }))
          .filter(({ ep }) => ep.generated !== true)
          .map(({ originalIndex }) => ({ originalIndex }))
      } else {
        // 用户点关闭 (close) 或按 Esc
        return
      }
    }
  } else {
    targets = sections.map((_, i) => ({ originalIndex: i }))
  }

  if (targets.length === 0) {
    ElMessage.info('没有需要生成的集')
    return
  }

  expandAllTotal.value = targets.length
  isExpandingAll.value = true
  let failCount = 0

  for (let i = 0; i < targets.length; i++) {
    const { originalIndex } = targets[i]
    expandAllCurrent.value = i + 1

    await new Promise<void>((resolve) => {
      const ctrl = streamExpandEpisode(
        projectId.value,
        originalIndex,
        () => { /* chunk 忽略 */ },
        async () => {
          currentAbortController.value = null
          await dramaStore.fetchSession(projectId.value)
          resolve()
        },
        (error) => {
          ElMessage.error(`第 ${originalIndex + 1} 集生成失败：${error}`)
          currentAbortController.value = null
          failCount++
          resolve()
        },
      )
      currentAbortController.value = ctrl
    })
  }

  isExpandingAll.value = false
  expandAllCurrent.value = 0
  currentAbortController.value = null

  if (failCount === targets.length) {
    ElMessage.error('全部集生成失败')
  } else if (failCount > 0) {
    ElMessage.warning(`${failCount} 集生成失败，其余已完成`)
  } else {
    ElMessage.success('全部内容生成完成')
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

    const sess = dramaStore.session
    const urlStep = Number(route.query.step) || 0

    // Restore questionCount from session
    if (sess) {
      if (sess.state === 'done' || sess.state === 'generating') {
        questionCount.value = 5
      } else if (sess.history) {
        const userMsgCount = sess.history.filter((m) => m.role === 'user').length
        questionCount.value = Math.min(userMsgCount, 5)
      }

      // Detect stuck "generating" state — no active generation but DB says generating
      if (sess.state === 'generating' && !generatingOutline.value && !regeneratingOutline.value) {
        ElMessage.warning('上次生成可能意外中断，请尝试重新生成大纲')
        sess.state = 'done' // Allow retry
      }
    }

    // Determine which step to show based on URL + session state
    if (dramaStore.nodes.length && dramaStore.currentProject?.status !== 'drafting') {
      // Nodes confirmed → outline review
      wizardStepIndex.value = 2
    } else if (urlStep === 2 && sess?.outline_draft) {
      // URL says step 2 and outline exists → stay on outline preview
      wizardStepIndex.value = 2
    } else if (urlStep === 1 && sess?.summary) {
      // URL says step 1 and summary saved → restore summary and stay
      sessionSummary.value = sess.summary as SessionSummary
      syncEditableSummary(sess.summary as SessionSummary)
      wizardStepIndex.value = 1
    } else {
      // Default to step 0 (Q&A)
      wizardStepIndex.value = 0
    }
  } catch {
    ElMessage.error('加载失败')
  } finally {
    pageLoading.value = false
  }
})

onUnmounted(() => {
  currentAbortController.value?.abort()
  isExpandingAll.value = false
  expandAllCurrent.value = 0
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

.summary-hint {
  font-size: 12px;
  color: #9E9E9E;
  margin: 4px 0 8px;
}

.character-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.character-row .el-input {
  flex: 1;
}

.field-hint {
  font-size: 12px;
  font-weight: 400;
  color: #9E9E9E;
  margin-left: 6px;
}

.field-counter {
  float: right;
  font-size: 12px;
  font-weight: 400;
  color: #9E9E9E;
}

.bios-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.bios-header h4 {
  margin: 0;
}

.bios-empty {
  font-size: 13px;
  color: #9E9E9E;
  padding: 12px 0;
  text-align: center;
  background: #F8F9FA;
  border: 1px dashed #E0E0E0;
  border-radius: 6px;
}

.bio-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  margin-bottom: 10px;
  background: #FAFBFC;
  border: 1px solid #E5E7EB;
  border-radius: 8px;
}

.bio-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bio-name {
  flex: 1;
}

.bio-name :deep(.el-input__inner) {
  font-weight: 600;
}

.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.role-tag {
  max-width: 100%;
  white-space: normal;
  height: auto;
  padding: 6px 12px;
  line-height: 1.4;
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
  overflow-y: auto;
  min-height: 300px;
  max-height: calc(100vh - 320px);
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
