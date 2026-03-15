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

      <el-tooltip content="根据当前内容续写，完成后自动追加到章节末尾" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('continue')"
        >
          <el-icon><Promotion /></el-icon>
          续写故事
        </el-button>
      </el-tooltip>

      <el-tooltip content="改写润色当前内容，完成后可选择替换原文" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('rewrite')"
        >
          <el-icon><Edit /></el-icon>
          改写润色
        </el-button>
      </el-tooltip>

      <el-tooltip content="根据您的意见修改内容，完成后自动覆盖原文" placement="left">
        <el-button
          class="ai-btn revise-btn"
          :disabled="generating || !currentContent"
          @click="showReviseDialog = true"
        >
          <el-icon><EditPen /></el-icon>
          意见修改
        </el-button>
      </el-tooltip>

      <el-tooltip content="扩写丰富当前内容，完成后可选择替换原文" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('expand')"
        >
          <el-icon><Plus /></el-icon>
          扩写内容
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将分析开头风格并扩写续写" placement="left">
        <el-button
          class="ai-btn"
          :disabled="generating"
          @click="handleAction('analyze_expand')"
        >
          <el-icon><Reading /></el-icon>
          开篇分析
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

      <el-tooltip content="AI 参考小说风格和知识库，批量生成前 X 章" placement="left">
        <el-button
          class="ai-btn batch-btn"
          :disabled="generating"
          @click="showBatchDialog = true"
        >
          <el-icon><Files /></el-icon>
          批量写作
        </el-button>
      </el-tooltip>
    </div>

    <!-- 批量生成对话框 -->
    <el-dialog
      :close-on-press-escape="false"
      v-model="showBatchDialog"
      title="AI 批量写作"
      width="480px"
      :close-on-click-modal="false"
    >
      <el-form label-width="100px" label-position="left">
        <el-form-item label="章节数量">
          <el-input-number
            v-model="batchForm.chapter_count"
            :min="1"
            :max="30"
            :step="1"
          />
          <span class="form-hint">章</span>
        </el-form-item>
        <el-form-item label="每章字数">
          <el-input-number
            v-model="batchForm.words_per_chapter"
            :min="500"
            :max="5000"
            :step="100"
          />
          <span class="form-hint">字</span>
        </el-form-item>
        <el-form-item label="参考小说">
          <el-select
            v-model="batchForm.reference_ids"
            multiple
            placeholder="选择参考小说（可选）"
            style="width: 100%"
            :loading="loadingRefs"
          >
            <el-option
              v-for="ref in referenceList"
              :key="ref.id"
              :label="ref.title"
              :value="ref.id"
            >
              <span>{{ ref.title }}</span>
              <span v-if="ref.writing_style" style="color: #9E9E9E; font-size: 12px; margin-left: 8px">有风格分析</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="使用知识库">
          <el-switch v-model="batchForm.use_knowledge" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showBatchDialog = false">取消</el-button>
        <el-button type="primary" @click="startBatchGenerate" :loading="batchGenerating">
          开始生成
        </el-button>
      </template>
    </el-dialog>

    <!-- 意见修改对话框 -->
    <el-dialog
      v-model="showReviseDialog"
      title="意见修改"
      width="500px"
      :close-on-click-modal="false"
    >
      <el-form label-position="top">
        <el-form-item label="修改意见">
          <el-input
            v-model="reviseOpinion"
            type="textarea"
            :rows="4"
            placeholder="请输入您的修改意见，例如：&#10;- 增加心理描写&#10;- 调整对话语气&#10;- 删除冗余段落"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showReviseDialog = false">取消</el-button>
        <el-button
          type="primary"
          @click="handleRevise"
          :loading="generating"
          :disabled="!reviseOpinion.trim()"
        >
          开始修改
        </el-button>
      </template>
    </el-dialog>

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
          <el-tooltip content="全屏查看">
            <el-button size="small" text @click="showFullscreen = true">
              <el-icon><FullScreen /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="复制到剪贴板">
            <el-button size="small" text @click="copyOutput">
              <el-icon><CopyDocument /></el-icon>
            </el-button>
          </el-tooltip>
          <el-tooltip content="替换当前章节内容" v-if="['rewrite', 'expand', 'analyze_expand'].includes(lastAction)">
            <el-button size="small" text type="primary" @click="replaceContent">
              <el-icon><RefreshRight /></el-icon>
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
      <div class="output-footer" v-if="outputText">
        <span class="output-word-count">{{ outputText.length }} 字</span>
      </div>
    </div>

    <!-- 全屏查看对话框 -->
    <el-dialog
      v-model="showFullscreen"
      title="AI 输出"
      width="90%"
      top="5vh"
      :close-on-click-modal="true"
      class="fullscreen-dialog"
    >
      <pre class="fullscreen-text">{{ outputText }}</pre>
      <template #footer>
        <div class="fullscreen-footer">
          <span class="output-word-count">{{ outputText.length }} 字</span>
          <div class="fullscreen-actions">
            <el-button @click="copyOutput">复制</el-button>
            <el-button v-if="['rewrite', 'expand', 'analyze_expand'].includes(lastAction)" type="primary" @click="replaceContent(); showFullscreen = false">替换原文</el-button>
            <el-button @click="showFullscreen = false">关闭</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted } from 'vue'
import { nextTick } from 'vue'
import {
  MagicStick, Promotion, Edit, Plus, Document, User, Reading,
  Loading, Check, CopyDocument, Bottom, Delete, Close, Files, RefreshRight, EditPen, FullScreen,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { streamGenerate, getAIConfig, streamBatchGenerate } from '@/api/ai'
import type { AIGenerateRequest, BatchGenerateEvent } from '@/api/ai'
import { getReferences } from '@/api/reference'
import type { ReferenceNovel } from '@/api/reference'

const props = defineProps<{
  currentChapterTitle?: string
  currentContent?: string
  projectId?: number
  chapterId?: number
}>()

const emit = defineEmits<{
  'insert-text': [text: string]
  'replace-text': [text: string]
  'chapters-updated': []
}>()

const generating = ref(false)
const outputText = ref('')
const lastAction = ref('')
const errorText = ref('')
const chatQuestion = ref('')
const currentProvider = ref('')
const outputRef = ref<HTMLElement | null>(null)

// 批量生成相关
const showBatchDialog = ref(false)
const batchGenerating = ref(false)
const loadingRefs = ref(false)
const referenceList = ref<ReferenceNovel[]>([])
const batchForm = ref({
  chapter_count: 5,
  words_per_chapter: 1500,
  reference_ids: [] as number[],
  use_knowledge: true,
})

// 意见修改相关
const showReviseDialog = ref(false)
const showFullscreen = ref(false)
const reviseOpinion = ref('')

let abortController: AbortController | null = null

// 加载参考小说列表
async function loadReferences() {
  loadingRefs.value = true
  try {
    referenceList.value = await getReferences()
  } catch {
    // 静默失败
  } finally {
    loadingRefs.value = false
  }
}

onMounted(async () => {
  try {
    const config = await getAIConfig()
    currentProvider.value = config.default_provider
  } catch {
    // 静默失败
  }
  loadReferences()
})

// 切换章节时清空 AI 输出和停止生成
watch(() => props.chapterId, () => {
  if (generating.value) {
    abortController?.abort()
    generating.value = false
  }
  outputText.value = ''
  errorText.value = ''
  lastAction.value = ''
})

function handleAction(action: AIGenerateRequest['action']) {
  if (!props.projectId) {
    ElMessage.warning('请先选择一个项目')
    return
  }

  const content = props.currentContent || ''
  if (!content && ['continue', 'rewrite', 'expand', 'analyze_expand'].includes(action)) {
    ElMessage.warning('当前章节没有内容，请先写一些文字')
    return
  }

  lastAction.value = action
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

// 意见修改：根据用户意见修改内容，完成后自动覆盖原文
function handleRevise() {
  if (!props.projectId || !reviseOpinion.value.trim() || !props.currentContent) return

  showReviseDialog.value = false
  lastAction.value = 'revise'

  startGeneration({
    action: 'revise',
    content: props.currentContent,
    question: reviseOpinion.value.trim(),
    chapter_id: props.chapterId,
  })
  reviseOpinion.value = ''
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
      if (!outputText.value) return

      if (lastAction.value === 'continue') {
        // 续写完成后自动追加到编辑器
        emit('insert-text', outputText.value)
        ElMessage.success('续写内容已追加到章节末尾')
      } else if (lastAction.value === 'revise') {
        // 意见修改完成后自动覆盖原文
        emit('replace-text', outputText.value)
        ElMessage.success('已根据意见修改并覆盖原文')
      } else if (['rewrite', 'expand'].includes(lastAction.value)) {
        // 改写润色、扩写完成后提示替换章节内容
        ElMessageBox.confirm('是否用 AI 生成的内容替换当前章节？', '替换确认', {
          confirmButtonText: '替换',
          cancelButtonText: '保留原文',
          type: 'info',
        }).then(() => {
          emit('replace-text', outputText.value)
          ElMessage.success('已替换章节内容')
        }).catch(() => {
          // 用户选择保留原文
        })
      }
    },
    (error) => {
      generating.value = false
      errorText.value = error
    },
  )
}

function startBatchGenerate() {
  if (!props.projectId) {
    ElMessage.warning('请先选择一个项目')
    return
  }

  showBatchDialog.value = false
  batchGenerating.value = true
  generating.value = true
  outputText.value = ''
  errorText.value = ''

  abortController = streamBatchGenerate(
    props.projectId,
    batchForm.value,
    (event: BatchGenerateEvent) => {
      switch (event.type) {
        case 'progress':
          outputText.value += `\n⏳ ${event.message}\n`
          break
        case 'outline':
          outputText.value += `\n📋 大纲生成完成：\n${event.text}\n`
          break
        case 'chapter_stream':
          outputText.value += event.text || ''
          break
        case 'chapter_done':
          outputText.value += `\n\n✅ 第${event.chapter_index}章「${event.title}」完成（${event.word_count}字）\n`
          break
        case 'done':
          outputText.value += `\n🎉 全部完成！共生成 ${event.total_chapters} 章\n`
          generating.value = false
          batchGenerating.value = false
          emit('chapters-updated')
          ElMessage.success(`批量生成完成，共 ${event.total_chapters} 章`)
          break
      }
      // 自动滚动
      nextTick(() => {
        if (outputRef.value) {
          outputRef.value.scrollTop = outputRef.value.scrollHeight
        }
      })
    },
    (error: string) => {
      generating.value = false
      batchGenerating.value = false
      errorText.value = error
    },
  )
}

function stopGeneration() {
  abortController?.abort()
  generating.value = false
}

function copyOutput() {
  const text = outputText.value
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => {
      ElMessage.success('已复制到剪贴板')
    }).catch(() => {
      fallbackCopy(text)
    })
  } else {
    fallbackCopy(text)
  }
}

function fallbackCopy(text: string) {
  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    document.execCommand('copy')
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
  document.body.removeChild(textarea)
}

function insertToEditor() {
  if (outputText.value) {
    emit('insert-text', outputText.value)
    ElMessage.success('已插入到编辑器')
  }
}

function replaceContent() {
  if (outputText.value) {
    emit('replace-text', outputText.value)
    ElMessage.success('已替换章节内容')
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
  background-color: white;
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid #f0ede6;
  margin-bottom: 16px;
}

.ai-icon {
  font-size: 20px;
  color: #6B7B8D;
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
  flex: 1;
}

.provider-tag {
  font-size: 10px;
}

.chapter-info {
  background: rgba(107, 123, 141, 0.05);
  border: 1px solid rgba(107, 123, 141, 0.12);
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 16px;
}

.info-label {
  font-size: 11px;
  color: #9E9E9E;
  margin-bottom: 4px;
}

.chapter-name {
  font-size: 13px;
  color: #6B7B8D;
  font-weight: 500;
}

.ai-actions {
  margin-bottom: 16px;
}

.section-title {
  font-size: 12px;
  color: #9E9E9E;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-btn {
  width: 100%;
  margin-bottom: 8px;
  background-color: #F7F6F3;
  border-color: #E0DFDC;
  color: #5C5C5C;
  justify-content: flex-start;
  gap: 8px;
  height: 40px;
  transition: all 0.2s;
}

.ai-btn:hover:not(:disabled) {
  border-color: #6B7B8D;
  background-color: rgba(107, 123, 141, 0.05);
  color: #6B7B8D;
}

.ai-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.batch-btn {
  border-color: #6B7B8D !important;
  background-color: rgba(107, 123, 141, 0.05) !important;
  color: #6B7B8D !important;
  font-weight: 500;
}

.batch-btn:hover:not(:disabled) {
  background-color: rgba(107, 123, 141, 0.10) !important;
}

.revise-btn {
  border-color: #e6a23c !important;
  background-color: rgba(230, 162, 60, 0.08) !important;
  color: #b88230 !important;
  font-weight: 500;
}

.revise-btn:hover:not(:disabled) {
  background-color: rgba(230, 162, 60, 0.15) !important;
  color: #cf9236 !important;
}

.form-hint {
  margin-left: 8px;
  color: #9E9E9E;
  font-size: 13px;
}

/* 自由对话区 */
.chat-input-area {
  margin-bottom: 16px;
}

.chat-input-wrap {
  position: relative;
}

.chat-input-wrap :deep(.el-textarea__inner) {
  background-color: #F7F6F3;
  border-color: #E0DFDC;
  color: #2C2C2C;
  resize: none;
  padding-right: 40px;
  border-radius: 8px;
}

.chat-input-wrap :deep(.el-textarea__inner):focus {
  border-color: #6B7B8D;
}

.send-btn {
  position: absolute;
  right: 4px;
  bottom: 4px;
}

/* AI 输出区域 */
.ai-output {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-top: 1px solid #f0ede6;
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
  color: #6B7B8D;
}

.output-actions {
  display: flex;
  gap: 2px;
}

.output-actions .el-button {
  color: #9E9E9E;
}

.output-actions .el-button:hover {
  color: #6B7B8D;
}

.stop-btn {
  color: #f56c6c !important;
}

.output-content {
  flex: 1;
  background: #F7F6F3;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  padding: 12px;
  overflow-y: auto;
  max-height: 400px;
}

.output-footer {
  display: flex;
  justify-content: flex-end;
  padding: 4px 0;
}

.output-word-count {
  font-size: 11px;
  color: #9E9E9E;
}

.generated-text {
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: 'Noto Serif SC', 'PingFang SC', sans-serif;
  margin: 0;
}

.error-text {
  color: #f56c6c;
  font-size: 13px;
}

.cursor-blink {
  animation: blink 1s step-end infinite;
  color: #6B7B8D;
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

/* 全屏对话框 */
.fullscreen-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  font-size: 15px;
  line-height: 2;
  color: #2C2C2C;
  max-height: 70vh;
  overflow-y: auto;
  padding: 16px;
  background: #FAFAF8;
  border-radius: 8px;
  font-family: inherit;
  margin: 0;
}

.fullscreen-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.fullscreen-actions {
  display: flex;
  gap: 8px;
}
</style>
