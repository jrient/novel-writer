<template>
  <el-drawer
    :model-value="visible"
    title="AI 配置"
    direction="rtl"
    size="420px"
    @update:model-value="emit('update:visible', $event)"
  >
    <div class="config-form">
      <!-- Provider -->
      <div class="form-section">
        <h4 class="section-title">模型配置</h4>

        <div class="form-item">
          <label class="form-label">服务商</label>
          <el-select v-model="form.provider" placeholder="选择 AI 服务商" style="width: 100%">
            <el-option label="OpenAI" value="openai" />
            <el-option label="Anthropic (Claude)" value="anthropic" />
            <el-option label="Google (Gemini)" value="google" />
            <el-option label="DeepSeek" value="deepseek" />
            <el-option label="通义千问" value="qwen" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </div>

        <div class="form-item">
          <label class="form-label">模型名称</label>
          <el-input v-model="form.model" placeholder="如：gpt-4o, claude-3-5-sonnet-20241022..." />
        </div>

        <div class="form-item">
          <label class="form-label">
            温度 (Temperature)
            <span class="label-hint">{{ form.temperature?.toFixed(1) }}</span>
          </label>
          <el-slider
            v-model="form.temperature"
            :min="0"
            :max="2"
            :step="0.1"
            :show-tooltip="false"
            class="config-slider"
          />
          <div class="slider-hints">
            <span>保守</span>
            <span>创意</span>
          </div>
        </div>

        <div class="form-item">
          <label class="form-label">最大 Token 数</label>
          <el-input-number
            v-model="form.max_tokens"
            :min="256"
            :max="32768"
            :step="256"
            style="width: 100%"
          />
        </div>
      </div>

      <!-- Prompt Templates -->
      <div class="form-section">
        <h4 class="section-title">提示词模板</h4>
        <p class="section-desc">留空则使用系统默认提示词</p>

        <div class="form-item">
          <label class="form-label">问答引导提示词</label>
          <el-input
            v-model="form.prompts.questioning"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="用于 AI 引导问答阶段的系统提示词..."
          />
        </div>

        <div class="form-item">
          <label class="form-label">大纲生成提示词</label>
          <el-input
            v-model="form.prompts.outlining"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="用于生成剧本大纲的系统提示词..."
          />
        </div>

        <div class="form-item">
          <label class="form-label">扩写提示词</label>
          <el-input
            v-model="form.prompts.expanding"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="用于扩写节点内容的系统提示词..."
          />
        </div>

        <div class="form-item">
          <label class="form-label">改写提示词</label>
          <el-input
            v-model="form.prompts.rewriting"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 6 }"
            placeholder="用于改写内容的系统提示词..."
          />
        </div>
      </div>
    </div>

    <template #footer>
      <div class="drawer-footer">
        <el-button @click="emit('update:visible', false)">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useDramaStore } from '@/stores/drama'
import type { ScriptProject } from '@/api/drama'

const props = defineProps<{
  visible: boolean
  project: ScriptProject | null
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
  (e: 'saved'): void
}>()

const dramaStore = useDramaStore()
const saving = ref(false)

const form = ref({
  provider: '',
  model: '',
  temperature: 0.7,
  max_tokens: 4096,
  prompts: {
    questioning: '',
    outlining: '',
    expanding: '',
    rewriting: '',
  },
})

watch(
  () => props.project,
  (project) => {
    if (project?.ai_config) {
      const cfg = project.ai_config
      form.value.provider = cfg.provider || ''
      form.value.model = cfg.model || ''
      form.value.temperature = cfg.temperature ?? 0.7
      form.value.max_tokens = cfg.max_tokens ?? 4096
      form.value.prompts = {
        questioning: cfg.prompts?.questioning || '',
        outlining: cfg.prompts?.outlining || '',
        expanding: cfg.prompts?.expanding || '',
        rewriting: cfg.prompts?.rewriting || '',
      }
    }
  },
  { immediate: true },
)

async function handleSave() {
  if (!props.project) return
  saving.value = true
  try {
    const config = {
      provider: form.value.provider || undefined,
      model: form.value.model || undefined,
      temperature: form.value.temperature,
      max_tokens: form.value.max_tokens,
      prompts: {
        questioning: form.value.prompts.questioning || undefined,
        outlining: form.value.prompts.outlining || undefined,
        expanding: form.value.prompts.expanding || undefined,
        rewriting: form.value.prompts.rewriting || undefined,
      },
    }
    await dramaStore.updateProjectAIConfig(props.project.id, config)
    ElMessage.success('AI 配置已保存')
    emit('saved')
    emit('update:visible', false)
  } catch {
    ElMessage.error('保存失败，请重试')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.config-form {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-bottom: 24px;
}

.form-section {
  padding: 0 0 20px;
  margin-bottom: 20px;
  border-bottom: 1px solid #ECEAE6;
}

.form-section:last-child {
  border-bottom: none;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0 0 4px;
  font-family: 'Noto Serif SC', serif;
}

.section-desc {
  font-size: 12px;
  color: #9E9E9E;
  margin: 0 0 14px;
}

.form-item {
  margin-bottom: 16px;
}

.form-item:last-child {
  margin-bottom: 0;
}

.form-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
  margin-bottom: 6px;
}

.label-hint {
  font-size: 13px;
  font-weight: 600;
  color: #6B7B8D;
}

.config-slider {
  margin: 4px 0;
}

.slider-hints {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: #9E9E9E;
  margin-top: 2px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

:deep(.el-slider__runway) {
  background: #E0DFDC;
}

:deep(.el-slider__bar) {
  background: linear-gradient(to right, #6B7B8D, #5A6B7A);
}

:deep(.el-slider__button) {
  border-color: #6B7B8D;
}
</style>
