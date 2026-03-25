<template>
  <div class="wizard-chat">
    <!-- 消息列表 -->
    <div class="messages-container" ref="messagesEl">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        :class="['message-row', msg.role === 'user' ? 'message-row--user' : 'message-row--ai']"
      >
        <!-- AI 消息 -->
        <template v-if="msg.role === 'ai'">
          <div class="avatar avatar--ai">AI</div>
          <div class="message-bubble message-bubble--ai">
            <template v-if="msg.parsed">
              <p class="question-text">{{ msg.parsed.question }}</p>
              <div v-if="msg.parsed.options?.length" class="options-list">
                <el-button
                  v-for="opt in msg.parsed.options"
                  :key="opt"
                  size="small"
                  class="option-btn"
                  @click="selectOption(opt)"
                  :disabled="isStreaming || idx < messages.length - 1"
                >
                  {{ opt }}
                </el-button>
              </div>
            </template>
            <template v-else>
              <p class="message-text">{{ msg.content }}</p>
            </template>
          </div>
        </template>

        <!-- 用户消息 -->
        <template v-else>
          <div class="message-bubble message-bubble--user">
            <p class="message-text">{{ msg.content }}</p>
          </div>
          <div class="avatar avatar--user">我</div>
        </template>
      </div>

      <!-- 流式输出中的临时气泡 -->
      <div v-if="streamingText" class="message-row message-row--ai">
        <div class="avatar avatar--ai">AI</div>
        <div class="message-bubble message-bubble--ai message-bubble--streaming">
          <p class="message-text">{{ streamingText }}</p>
          <span class="streaming-cursor">▍</span>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="isStreaming && !streamingText" class="message-row message-row--ai">
        <div class="avatar avatar--ai">AI</div>
        <div class="message-bubble message-bubble--ai">
          <span class="typing-dots"><span></span><span></span><span></span></span>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="input-area">
      <el-input
        v-model="inputText"
        placeholder="输入回答，或点击上方选项..."
        :disabled="isStreaming"
        @keydown.enter.exact.prevent="sendMessage"
        class="chat-input"
        maxlength="500"
      />
      <el-button
        v-if="isStreaming"
        type="danger"
        plain
        @click="stopStreaming"
        class="send-btn"
      >
        停止
      </el-button>
      <el-button
        v-else
        type="primary"
        :icon="Promotion"
        :disabled="!inputText.trim()"
        @click="sendMessage"
        class="send-btn"
      >
        发送
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Promotion } from '@element-plus/icons-vue'
import {
  streamSessionAnswer,
  streamGenerateOutline,
  getOrCreateSession,
} from '@/api/drama'
import type { ScriptSession } from '@/api/drama'

interface ChatMessage {
  role: 'ai' | 'user'
  content: string
  parsed?: { question: string; options?: string[] }
}

const props = defineProps<{
  projectId: number
  session: ScriptSession | null
}>()

const emit = defineEmits<{
  (e: 'outline-ready'): void
}>()

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const isStreaming = ref(false)
const streamingText = ref('')
const messagesEl = ref<HTMLElement>()

let abortController: AbortController | null = null

function stopStreaming() {
  abortController?.abort()
  abortController = null
  isStreaming.value = false
  streamingText.value = ''
}

function parseAiMessage(content: string): ChatMessage['parsed'] | undefined {
  try {
    const json = JSON.parse(content)
    if (json.question) {
      return { question: json.question, options: json.options || [] }
    }
  } catch {
    // not JSON
  }
  return undefined
}

function addAiMessage(content: string) {
  const parsed = parseAiMessage(content)
  messages.value.push({ role: 'ai', content, parsed })
}

async function scrollToBottom() {
  await nextTick()
  if (messagesEl.value) {
    messagesEl.value.scrollTop = messagesEl.value.scrollHeight
  }
}

function selectOption(opt: string) {
  inputText.value = opt
  sendMessage()
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || isStreaming.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  await scrollToBottom()

  isStreaming.value = true
  streamingText.value = ''

  abortController = streamSessionAnswer(
    props.projectId,
    text,
    (chunk) => {
      streamingText.value += chunk
      scrollToBottom()
    },
    async (fullResponse) => {
      const finalText = (fullResponse as string) || streamingText.value
      streamingText.value = ''
      isStreaming.value = false

      if (finalText.includes('"done":true') || finalText === '__done__') {
        // Questioning complete, generate outline
        await generateOutline()
      } else {
        addAiMessage(finalText)
        await scrollToBottom()
      }
    },
    (error) => {
      streamingText.value = ''
      isStreaming.value = false
      ElMessage.error('发送失败：' + error)
    },
  )
}

async function generateOutline() {
  isStreaming.value = true
  streamingText.value = ''

  messages.value.push({
    role: 'ai',
    content: '好的，我将根据你的回答生成剧本大纲...',
    parsed: undefined,
  })
  await scrollToBottom()

  abortController = streamGenerateOutline(
    props.projectId,
    (chunk) => {
      streamingText.value += chunk
      scrollToBottom()
    },
    async () => {
      streamingText.value = ''
      isStreaming.value = false
      messages.value.push({
        role: 'ai',
        content: '大纲已生成！请在下方查看并确认。',
        parsed: undefined,
      })
      await scrollToBottom()
      emit('outline-ready')
    },
    (error) => {
      streamingText.value = ''
      isStreaming.value = false
      ElMessage.error('生成大纲失败：' + error)
    },
  )
}

onMounted(async () => {
  // Load existing history from session
  if (props.session?.history?.length) {
    for (const msg of props.session.history) {
      if (msg.role === 'assistant') {
        addAiMessage(msg.content)
      } else if (msg.role === 'user') {
        messages.value.push({ role: 'user', content: msg.content })
      }
    }
  } else {
    // Fresh session — get first question from server
    isStreaming.value = true
    try {
      const session = await getOrCreateSession(props.projectId)
      if (session.history?.length) {
        for (const msg of session.history) {
          if (msg.role === 'assistant') {
            addAiMessage(msg.content)
          }
        }
      } else {
        // Trigger first question by sending empty init
        // Show a welcome message
        addAiMessage(JSON.stringify({
          question: '你好！我将通过几个问题帮你完善剧本创意。我们开始吧，请先介绍一下你的故事主线是什么？',
          options: [],
        }))
      }
    } catch {
      ElMessage.error('加载会话失败')
    } finally {
      isStreaming.value = false
    }
  }
  await scrollToBottom()
})
</script>

<style scoped>
.wizard-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.messages-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  scroll-behavior: smooth;
}

.message-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.message-row--user {
  flex-direction: row-reverse;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.avatar--ai {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  color: white;
}

.avatar--user {
  background: #E8F4F0;
  color: #4A7A6A;
}

.message-bubble {
  max-width: 68%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
}

.message-bubble--ai {
  background: white;
  border: 1px solid #E0DFDC;
  border-top-left-radius: 4px;
}

.message-bubble--user {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  color: white;
  border-top-right-radius: 4px;
}

.message-bubble--streaming {
  border-color: #6B7B8D;
}

.message-text {
  margin: 0;
  font-size: 14px;
  color: inherit;
  white-space: pre-wrap;
}

.question-text {
  margin: 0 0 10px;
  font-size: 14px;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
}

.options-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.option-btn {
  border-color: #6B7B8D !important;
  color: #6B7B8D !important;
  background: transparent !important;
  transition: all 0.2s;
}

.option-btn:hover:not(:disabled) {
  background: rgba(107, 123, 141, 0.08) !important;
}

.streaming-cursor {
  display: inline-block;
  animation: blink 0.8s infinite;
  color: #6B7B8D;
  font-weight: bold;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

.typing-dots {
  display: inline-flex;
  gap: 4px;
  align-items: center;
  height: 20px;
}

.typing-dots span {
  width: 6px;
  height: 6px;
  background: #9E9E9E;
  border-radius: 50%;
  animation: typing 1.2s infinite;
}

.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.5; }
  30% { transform: translateY(-6px); opacity: 1; }
}

.input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid #E0DFDC;
  background: white;
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
}

.send-btn {
  flex-shrink: 0;
}
</style>
