<template>
  <div class="drama-create-page">
    <!-- Header -->
    <header class="page-header">
      <div class="header-content">
        <div class="logo-area" @click="router.push('/drama')">
          <span class="logo-icon">&#127916;</span>
          <h1 class="logo">剧本创作</h1>
        </div>
        <el-button text @click="router.push('/drama')">
          <el-icon><ArrowLeft /></el-icon> 返回列表
        </el-button>
      </div>
    </header>

    <!-- Steps -->
    <div class="steps-container">
      <el-steps :active="currentStep - 1" align-center>
        <el-step title="选择类型" description="确定剧本形式" />
        <el-step title="填写创意" description="描述故事概念" />
        <el-step title="AI 配置" description="可选，自定义模型" />
      </el-steps>
    </div>

    <!-- Step content -->
    <main class="page-main">
      <transition name="fade" mode="out-in">

        <!-- Step 1: Type selection -->
        <div v-if="currentStep === 1" class="step-content" key="step1">
          <h2 class="step-title">选择剧本类型</h2>
          <p class="step-desc">不同类型的剧本有不同的节点结构和创作风格</p>

          <div class="type-cards">
            <div
              class="type-card"
              :class="{ 'type-card--selected': form.script_type === 'explanatory' }"
              @click="form.script_type = 'explanatory'"
            >
              <div class="type-icon">&#127902;</div>
              <h3 class="type-name">解说漫</h3>
              <p class="type-desc">以旁白解说为主导，配合画面讲述故事。适合知识类、纪录片风格的漫画创作。</p>
              <ul class="type-features">
                <li>章节 → 段落 → 旁白/介绍</li>
                <li>画面描述驱动</li>
                <li>适合知识、历史、科普题材</li>
              </ul>
              <div v-if="form.script_type === 'explanatory'" class="type-check">
                <el-icon><Select /></el-icon>
              </div>
            </div>

            <div
              class="type-card"
              :class="{ 'type-card--selected': form.script_type === 'dynamic' }"
              @click="form.script_type = 'dynamic'"
            >
              <div class="type-icon">&#127916;</div>
              <h3 class="type-name">动态漫</h3>
              <p class="type-desc">以人物对话和动作推进情节，具有戏剧张力。适合故事类、角色驱动的漫画创作。</p>
              <ul class="type-features">
                <li>集 → 场景 → 对白/动作/特效</li>
                <li>角色对话驱动</li>
                <li>适合故事、冒险、情感题材</li>
              </ul>
              <div v-if="form.script_type === 'dynamic'" class="type-check">
                <el-icon><Select /></el-icon>
              </div>
            </div>
          </div>

          <div class="step-actions">
            <el-button
              type="primary"
              size="large"
              :disabled="!form.script_type"
              @click="currentStep = 2"
              round
            >
              下一步
            </el-button>
          </div>
        </div>

        <!-- Step 2: Title & Concept -->
        <div v-else-if="currentStep === 2" class="step-content" key="step2">
          <h2 class="step-title">描述你的故事</h2>
          <p class="step-desc">AI 将根据这些信息为你提供个性化的创作引导</p>

          <div class="form-card">
            <div class="form-item">
              <label class="form-label">剧本标题 <span class="required">*</span></label>
              <el-input
                v-model="form.title"
                placeholder="起一个有吸引力的标题..."
                maxlength="100"
                show-word-limit
                size="large"
              />
            </div>

            <div class="form-item">
              <label class="form-label">故事创意 <span class="required">*</span></label>
              <el-input
                v-model="form.concept"
                type="textarea"
                :autosize="{ minRows: 5, maxRows: 12 }"
                :placeholder="conceptPlaceholder"
                maxlength="2000"
                show-word-limit
              />
            </div>
          </div>

          <div class="step-actions">
            <el-button size="large" @click="currentStep = 1" round>上一步</el-button>
            <el-button size="large" @click="currentStep = 3" round>配置 AI（可选）</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="creating"
              :disabled="!form.title.trim() || !form.concept.trim()"
              @click="handleCreate"
              round
            >
              直接创建
            </el-button>
          </div>
        </div>

        <!-- Step 3: AI Config (optional) -->
        <div v-else-if="currentStep === 3" class="step-content" key="step3">
          <h2 class="step-title">AI 配置 <span class="optional-badge">可选</span></h2>
          <p class="step-desc">不配置将使用系统默认的 AI 设置，可随时在工作台修改</p>

          <div class="form-card">
            <div class="form-item">
              <label class="form-label">服务商</label>
              <el-select v-model="aiConfig.provider" placeholder="使用默认" style="width: 100%" clearable>
                <el-option label="OpenAI" value="openai" />
                <el-option label="Anthropic (Claude)" value="anthropic" />
                <el-option label="Google (Gemini)" value="google" />
                <el-option label="DeepSeek" value="deepseek" />
                <el-option label="通义千问" value="qwen" />
              </el-select>
            </div>

            <div class="form-item">
              <label class="form-label">模型名称</label>
              <el-input v-model="aiConfig.model" placeholder="留空使用默认模型" clearable />
            </div>

            <div class="form-item">
              <label class="form-label">
                温度 (Temperature)
                <span class="label-value">{{ aiConfig.temperature?.toFixed(1) }}</span>
              </label>
              <el-slider
                v-model="aiConfig.temperature"
                :min="0"
                :max="2"
                :step="0.1"
                :show-tooltip="false"
              />
              <div class="slider-hints">
                <span>保守</span>
                <span>创意</span>
              </div>
            </div>
          </div>

          <div class="step-actions">
            <el-button size="large" @click="currentStep = 2" round>上一步</el-button>
            <el-button
              type="primary"
              size="large"
              :loading="creating"
              @click="handleCreate"
              round
            >
              创建并开始引导
            </el-button>
          </div>
        </div>

      </transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft, Select } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useDramaStore } from '@/stores/drama'

const router = useRouter()
const dramaStore = useDramaStore()

const currentStep = ref(1)
const creating = ref(false)

const form = ref({
  title: '',
  script_type: '' as 'explanatory' | 'dynamic' | '',
  concept: '',
})

const aiConfig = ref({
  provider: '',
  model: '',
  temperature: 0.7,
})

const conceptPlaceholder = computed(() => {
  if (form.value.script_type === 'explanatory') {
    return '例如：一部介绍中国四大发明的知识漫画，从造纸术说起，通过现代人穿越到古代亲眼见证发明过程的视角来讲述...'
  }
  return '例如：一个少年在废土世界中寻找失散家人的故事，途中结识了形形色色的伙伴，共同对抗统治集团...'
})

async function handleCreate() {
  if (!form.value.title.trim() || !form.value.concept.trim() || !form.value.script_type) {
    ElMessage.warning('请填写完整信息')
    return
  }

  creating.value = true
  try {
    const data: Parameters<typeof dramaStore.createProject>[0] = {
      title: form.value.title.trim(),
      script_type: form.value.script_type,
      concept: form.value.concept.trim(),
    }

    if (aiConfig.value.provider || aiConfig.value.model) {
      data.ai_config = {
        provider: aiConfig.value.provider || undefined,
        model: aiConfig.value.model || undefined,
        temperature: aiConfig.value.temperature,
      }
    }

    const project = await dramaStore.createProject(data)
    ElMessage.success('剧本项目已创建')
    router.push(`/drama/wizard/${project.id}`)
  } catch {
    ElMessage.error('创建失败，请重试')
  } finally {
    creating.value = false
  }
}
</script>

<style scoped>
.drama-create-page {
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
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.steps-container {
  max-width: 700px;
  margin: 0 auto;
  padding: 32px 32px 0;
}

.page-main {
  max-width: 800px;
  margin: 0 auto;
  padding: 32px;
}

.step-content {
  text-align: center;
}

.step-title {
  font-size: 28px;
  font-weight: 700;
  color: #2C2C2C;
  margin-bottom: 8px;
  font-family: 'Noto Serif SC', serif;
}

.step-desc {
  font-size: 14px;
  color: #7A7A7A;
  margin-bottom: 32px;
}

.optional-badge {
  font-size: 13px;
  font-weight: 400;
  color: #9E9E9E;
  background: #F0EFEC;
  padding: 2px 10px;
  border-radius: 12px;
  vertical-align: middle;
  font-family: system-ui, sans-serif;
}

/* Type cards */
.type-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
  text-align: left;
}

.type-card {
  position: relative;
  background: white;
  border: 2px solid #E0DFDC;
  border-radius: 16px;
  padding: 28px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.type-card:hover {
  border-color: #6B7B8D;
  box-shadow: 0 4px 16px rgba(107, 123, 141, 0.12);
  transform: translateY(-2px);
}

.type-card--selected {
  border-color: #6B7B8D;
  background: rgba(107, 123, 141, 0.03);
  box-shadow: 0 4px 16px rgba(107, 123, 141, 0.12);
}

.type-icon {
  font-size: 40px;
  margin-bottom: 12px;
}

.type-name {
  font-size: 20px;
  font-weight: 700;
  color: #2C2C2C;
  margin: 0 0 10px;
  font-family: 'Noto Serif SC', serif;
}

.type-desc {
  font-size: 13px;
  color: #7A7A7A;
  line-height: 1.6;
  margin-bottom: 14px;
}

.type-features {
  list-style: none;
  padding: 0;
  margin: 0;
}

.type-features li {
  font-size: 12px;
  color: #9E9E9E;
  padding: 3px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}

.type-features li::before {
  content: '·';
  color: #6B7B8D;
  font-size: 18px;
  line-height: 1;
}

.type-check {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 24px;
  height: 24px;
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 14px;
}

/* Form card */
.form-card {
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 16px;
  padding: 28px;
  text-align: left;
  margin-bottom: 32px;
}

.form-item {
  margin-bottom: 20px;
}

.form-item:last-child { margin-bottom: 0; }

.form-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
  margin-bottom: 8px;
}

.required {
  color: #f56c6c;
  margin-left: 2px;
}

.label-value {
  font-weight: 600;
  color: #6B7B8D;
}

.slider-hints {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #9E9E9E;
  margin-top: 4px;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 12px;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Steps overrides */
:deep(.el-step__title) { font-size: 13px; }
:deep(.el-step__description) { font-size: 11px; }
:deep(.el-step.is-process .el-step__title) { color: #6B7B8D; }
:deep(.el-step.is-process .el-step__icon) { border-color: #6B7B8D; color: #6B7B8D; }
:deep(.el-step.is-finish .el-step__title) { color: #6B7B8D; }
:deep(.el-step.is-finish .el-step__icon) { border-color: #6B7B8D; color: #6B7B8D; }
:deep(.el-slider__bar) { background: linear-gradient(to right, #6B7B8D, #5A6B7A); }
:deep(.el-slider__button) { border-color: #6B7B8D; }

@media (max-width: 600px) {
  .type-cards { grid-template-columns: 1fr; }
  .page-main { padding: 16px; }
  .steps-container { padding: 16px 16px 0; }
}
</style>
