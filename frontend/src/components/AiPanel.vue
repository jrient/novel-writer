<template>
  <div class="ai-panel">
    <!-- 面板标题 -->
    <div class="panel-header">
      <el-icon class="ai-icon"><MagicStick /></el-icon>
      <h3>AI 助手</h3>
      <el-tag v-if="currentProvider" size="small" type="info" class="provider-tag">
        {{ currentProvider }}
      </el-tag>
    </div>

    <!-- 当前章节信息 -->
    <div class="chapter-info" v-if="currentChapterTitle">
      <p class="info-label">当前章节</p>
      <p class="chapter-name">{{ currentChapterTitle }}</p>
    </div>

    <!-- AI 功能按钮组 -->
    <div class="ai-actions">
      <p class="section-title">创作辅助</p>

      <el-tooltip content="AI 将根据当前内容续写故事" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('continue')"
        >
          <el-icon><Promotion /></el-icon>
          续写故事
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将改写润色当前内容" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('rewrite')"
        >
          <el-icon><Edit /></el-icon>
          改写润色
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将扩写丰富当前内容" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('expand')"
        >
          <el-icon><Plus /></el-icon>
          扩写内容
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将为故事生成章节大纲" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('outline')"
        >
          <el-icon><Document /></el-icon>
          生成大纲
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将分析角色性格与发展" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('character_analysis')"
        >
          <el-icon><User /></el-icon>
          角色分析
        </el-button>
      </el-tooltip>
    </div>

    <!-- 自由对话输入 -->
    <div class="chat-input-area">
      <p class="section-title">自由提问</p>
      <div class="chat-input-wrap">
        <el-input
          v-model="chatQuestion"
          type="textarea"
          :rows="2"
          placeholder="输入你的创作问题..."
          :disabled="generating"
          @keydown.ctrl.enter="handleFreeChat"
        />
        <el-button
          type="primary"
          size="small"
          class="send-btn"
          :disabled="generating || !chatQuestion.trim()"
          @click="handleFreeChat"
        >
          <el-icon><Promotion /></el-icon>
        </el-button>
      </div>
    </div>

    <!-- AI 输出区域 -->
    <div class="ai-output" v-if="outputText || generating || errorText">
      <div class="output-header">
        <span class="output-label">
          <el-icon v-if="generating" class="rotating"><Loading /></el-icon>
          <el-icon v-else><Check /></el-icon>
          {{ generating ? 'AI 生成中...' : 'AI 输出' }}
        </span>
        <div class="output-actions" v-if="outputText && !generating">
          <el-tooltip content="复制到剪贴板">
            <el-button size="small" text @click="copyOutput">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="插入到编辑器末尾">
            <el-button size="small" text @click="insertToEditor">
              <el-icon><Bottom /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="清空输出">
            <el-button size="small" text @click="clearOutput">
              <el-icon><Delete /></el-icon>
            </el-button>
          </el-tooltip>
        </div>
        <el-button v-if="generating" size="small" text @click="stopGeneration" class="stop-btn">
          <el-icon><Close /></el-icon>
          停止
        </el-button>
      </div>
      <div class="output-content" ref="outputRef">
        <p v-if="errorText" class="error-text">{{ errorText }}</p>
        <pre v-else class="generated-text">{{ outputText }}<span v-if="generating" class="cursor-blink">|</span></pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { nextTick } from 'vue'
import {
  MagicStick, Promotion, Edit, Plus, Document, User,
  Loading, Check, CopyDocument, Bottom, Delete, Close,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { streamGenerate, getAIConfig } from '@/api/ai'
import type { AIGenerateRequest } from '@/api/ai'

const props = defineProps<{
  currentChapterTitle?: string
  currentContent?: string
  projectId?: number
  chapterId?: number
}>()

const emit = defineEmits<{
  'insert-text': [text: string]
}>()

const generating = ref(false)
const outputText = ref('')
const errorText = ref('')
const chatQuestion = ref('')
const currentProvider = ref('')
const outputRef = ref<HTMLElement | null>(null)

let abortController: AbortController | null = null

onMounted(async () => {
  try {
    const config = await getAIConfig()
    currentProvider.value = config.default_provider
  } catch {
    // 静默失败
  }
})

function handleAction(action: AIGenerateRequest['action']) {
  if (!props.projectId) {
    ElMessage.warning('请先选择一个项目')
    return
  }

  const content = props.currentContent || ''
  if (!content && ['continue', 'rewrite', 'expand'].includes(action)) {
    ElMessage.warning('当前章节没有内容，请先写一些文字')
    return
  }

  startGeneration({
    action,
    content,
    chapter_id: props.chapterId,
  })
}

function handleFreeChat() {
  if (!props.projectId || !chatQuestion.value.trim()) return

  startGeneration({
    action: 'free_chat',
    content: props.currentContent || '',
    question: chatQuestion.value.trim(),
    chapter_id: props.chapterId,
  })
  chatQuestion.value = ''
}

function startGeneration(data: AIGenerateRequest) {
  if (generating.value) return

  generating.value = true
  outputText.value = ''
  errorText.value = ''

  abortController = streamGenerate(
    props.projectId!,
    data,
    (text) => {
      outputText.value += text
      // 自动滚动到底部
      nextTick(() => {
        if (outputRef.value) {
          outputRef.value.scrollTop = outputRef.value.scrollHeight
        }
      })
    },
    () => {
      generating.value = false
    },
    (error) => {
      generating.value = false
      errorText.value = error
    },
  )
}

function stopGeneration() {
  abortController?.abort()
  generating.value = false
}

function copyOutput() {
  navigator.clipboard.writeText(outputText.value).then(() => {
    ElMessage.success('已复制到剪贴板')
  })
}

function insertToEditor() {
  if (outputText.value) {
    emit('insert-text', outputText.value)
    ElMessage.success('已插入到编辑器')
  }
}

function clearOutput() {
  outputText.value = ''
  errorText.value = ''
}
</script>

<style scoped>
.ai-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  background-color: #16213e;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid #2d3561;
  margin-bottom: 16px;
}

.ai-icon {
  font-size: 20px;
  color: #e2b714;
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #e0e0e0;
  margin: 0;
  flex: 1;
}

.provider-tag {
  font-size: 10px;
}

.chapter-info {
  background: rgba(226, 183, 20, 0.05);
  border: 1px solid rgba(226, 183, 20, 0.2);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 16px;
}

.info-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
}

.chapter-name {
  font-size: 13px;
  color: #e2b714;
  font-weight: 500;
}

.ai-actions {
  margin-bottom: 16px;
}

.section-title {
  font-size: 12px;
  color: #606266;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-btn {
  width: 100%;
  margin-bottom: 8px;
  background-color: #1a1a2e;
  border-color: #2d3561;
  color: #c0c4cc;
  justify-content: flex-start;
  gap: 8px;
  height: 40px;
  transition: all 0.2s;
}

.ai-btn:hover:not(:disabled) {
  border-color: #e2b714;
  background-color: rgba(226, 183, 20, 0.1);
  color: #e2b714;
}

.ai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 自由对话区 */
.chat-input-area {
  margin-bottom: 16px;
}

.chat-input-wrap {
  position: relative;
}

.chat-input-wrap :deep(.el-textarea__inner) {
  background-color: #1a1a2e;
  border-color: #2d3561;
  color: #e0e0e0;
  resize: none;
  padding-right: 40px;
}

.chat-input-wrap :deep(.el-textarea__inner):focus {
  border-color: #e2b714;
}

.send-btn {
  position: absolute;
  right: 4px;
  bottom: 4px;
  background-color: #e2b714 !important;
  border-color: #e2b714 !important;
  color: #1a1a2e !important;
}

/* AI 输出区域 */
.ai-output {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-top: 1px solid #2d3561;
  padding-top: 12px;
  min-height: 150px;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.output-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #e2b714;
}

.output-actions {
  display: flex;
  gap: 2px;
}

.output-actions .el-button {
  color: #909399;
}

.output-actions .el-button:hover {
  color: #e2b714;
}

.stop-btn {
  color: #f56c6c !important;
}

.output-content {
  flex: 1;
  background: #1a1a2e;
  border: 1px solid #2d3561;
  border-radius: 6px;
  padding: 12px;
  overflow-y: auto;
  max-height: 400px;
}

.generated-text {
  font-size: 13px;
  line-height: 1.8;
  color: #e0e0e0;
  white-space: pre-wrap;
  word-break: break-all;
  font-family: 'Noto Serif SC', 'PingFang SC', sans-serif;
  margin: 0;
}

.error-text {
  color: #f56c6c;
  font-size: 13px;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: #e2b714;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
