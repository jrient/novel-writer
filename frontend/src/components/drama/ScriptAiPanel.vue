<template>
  <div class="ai-panel">
    <div class="panel-header">
      <span class="panel-title">AI 助手</span>
      <el-button text size="small" @click="emit('toggle')" class="collapse-btn">
        <el-icon><ArrowRight /></el-icon>
      </el-button>
    </div>

    <!-- No node warning -->
    <div v-if="!node" class="no-node-tip">
      <el-icon><InfoFilled /></el-icon>
      <span>请先选择一个节点</span>
    </div>

    <template v-else>
      <!-- Action buttons -->
      <div class="action-section">
        <p class="section-label">操作</p>
        <div class="action-buttons">
          <el-button
            size="small"
            class="action-btn"
            :loading="isStreaming && activeAction === 'expand'"
            @click="handleExpand"
          >
            <el-icon><MagicStick /></el-icon>
            扩写本节点
          </el-button>
          <el-button
            size="small"
            class="action-btn"
            :loading="isStreaming && activeAction === 'rewrite'"
            @click="showRewriteInput = !showRewriteInput"
          >
            <el-icon><Edit /></el-icon>
            重写 / 润色
          </el-button>
        </div>

        <!-- Rewrite instruction input -->
        <div v-if="showRewriteInput" class="rewrite-input">
          <el-input
            v-model="rewriteInstruction"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="输入改写指令，如：使语气更正式..."
            size="small"
          />
          <el-button
            size="small"
            type="primary"
            :loading="isStreaming && activeAction === 'rewrite'"
            @click="handleRewrite"
            style="margin-top: 8px; width: 100%"
          >
            执行改写
          </el-button>
        </div>
      </div>

      <!-- Streaming output area -->
      <div class="output-section">
        <div class="output-header">
          <p class="section-label">AI 输出</p>
          <el-button
            v-if="isStreaming"
            text
            size="small"
            type="danger"
            @click="stopStreaming"
          >
            停止
          </el-button>
        </div>
        <div class="output-area" ref="outputEl">
          <div v-if="!outputText && !isStreaming" class="output-placeholder">
            点击上方按钮让 AI 生成内容
          </div>
          <div v-else class="output-text">
            {{ outputText }}
            <span v-if="isStreaming" class="cursor">▍</span>
          </div>
        </div>
      </div>

      <!-- Apply button -->
      <div v-if="outputText && !isStreaming" class="apply-section">
        <el-button type="primary" size="small" style="width: 100%" @click="applyOutput">
          应用到编辑器
        </el-button>
        <el-button size="small" style="width: 100%; margin-top: 6px" @click="outputText = ''">
          清除
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { ArrowRight, MagicStick, Edit, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { streamExpandNode, streamRewrite } from '@/api/drama'
import type { ScriptNode } from '@/api/drama'

const props = defineProps<{
  projectId: number
  node: ScriptNode | null
  scriptType: 'explanatory' | 'dynamic'
}>()

const emit = defineEmits<{
  (e: 'toggle'): void
  (e: 'apply', text: string): void
}>()

const isStreaming = ref(false)
const activeAction = ref<'expand' | 'rewrite' | null>(null)
const outputText = ref('')
const showRewriteInput = ref(false)
const rewriteInstruction = ref('')
const outputEl = ref<HTMLElement>()

let abortController: AbortController | null = null

watch(() => props.node, () => {
  outputText.value = ''
  showRewriteInput.value = false
  rewriteInstruction.value = ''
})

async function scrollOutput() {
  await nextTick()
  if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight
}

function stopStreaming() {
  abortController?.abort()
  isStreaming.value = false
  activeAction.value = null
}

function handleExpand() {
  if (!props.node || isStreaming.value) return
  outputText.value = ''
  isStreaming.value = true
  activeAction.value = 'expand'

  abortController = streamExpandNode(
    props.projectId,
    props.node.id,
    (chunk) => {
      outputText.value += chunk
      scrollOutput()
    },
    () => {
      isStreaming.value = false
      activeAction.value = null
    },
    (error) => {
      isStreaming.value = false
      activeAction.value = null
      ElMessage.error('扩写失败：' + error)
    },
  )
}

function handleRewrite() {
  if (!props.node || isStreaming.value) return
  if (!rewriteInstruction.value.trim()) {
    ElMessage.warning('请输入改写指令')
    return
  }

  outputText.value = ''
  isStreaming.value = true
  activeAction.value = 'rewrite'

  abortController = streamRewrite(
    props.projectId,
    {
      content: props.node.content || '',
      instruction: rewriteInstruction.value,
      node_id: props.node.id,
    },
    (chunk) => {
      outputText.value += chunk
      scrollOutput()
    },
    () => {
      isStreaming.value = false
      activeAction.value = null
    },
    (error) => {
      isStreaming.value = false
      activeAction.value = null
      ElMessage.error('改写失败：' + error)
    },
  )
}

function applyOutput() {
  if (outputText.value) {
    emit('apply', outputText.value)
    ElMessage.success('已应用到编辑器')
  }
}
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 10px;
  border-bottom: 1px solid #ECEAE6;
  flex-shrink: 0;
}

.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: #5C5C5C;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.collapse-btn {
  color: #9E9E9E !important;
}

.no-node-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px;
  color: #9E9E9E;
  font-size: 13px;
}

.action-section,
.output-section,
.apply-section {
  padding: 12px 14px;
  border-bottom: 1px solid #ECEAE6;
  flex-shrink: 0;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: #9E9E9E;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin: 0 0 8px;
}

.action-buttons {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.action-btn {
  width: 100%;
  justify-content: flex-start;
  color: #5C5C5C !important;
  border-color: #E0DFDC !important;
}

.action-btn:hover {
  border-color: #6B7B8D !important;
  color: #6B7B8D !important;
  background: rgba(107, 123, 141, 0.04) !important;
}

.rewrite-input {
  margin-top: 10px;
}

.output-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-bottom: none;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.output-area {
  flex: 1;
  overflow-y: auto;
  background: #F7F6F3;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  padding: 12px;
}

.output-placeholder {
  font-size: 13px;
  color: #C0BDB9;
  text-align: center;
  padding: 24px 0;
}

.output-text {
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  font-family: 'Noto Serif SC', serif;
}

.cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
  color: #6B7B8D;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.apply-section {
  padding: 12px 14px;
  border-top: 1px solid #ECEAE6;
  flex-shrink: 0;
}
</style>
