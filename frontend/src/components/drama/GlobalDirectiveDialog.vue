<template>
  <el-dialog
    :model-value="visible"
    title="全局指令"
    width="580px"
    :close-on-click-modal="false"
    @update:model-value="emit('update:visible', $event)"
    @closed="resetForm"
  >
    <div class="directive-form">
      <div class="form-item">
        <label class="form-label">指令内容</label>
        <el-input
          v-model="instruction"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 8 }"
          placeholder="输入全局指令，如：将所有对白改为更口语化的风格..."
          maxlength="1000"
          show-word-limit
        />
      </div>

      <div class="form-item">
        <label class="form-label">作用范围</label>
        <el-radio-group v-model="scope" class="scope-radios">
          <el-radio value="outline">仅大纲</el-radio>
          <el-radio value="all_nodes">全部节点</el-radio>
          <el-radio value="selected_nodes">选中节点</el-radio>
        </el-radio-group>
      </div>

      <!-- Node selector for selected_nodes scope -->
      <div v-if="scope === 'selected_nodes'" class="form-item">
        <label class="form-label">选择节点</label>
        <el-select
          v-model="selectedNodeIds"
          multiple
          placeholder="选择要处理的节点"
          style="width: 100%"
          collapse-tags
          collapse-tags-tooltip
        >
          <el-option
            v-for="node in flatNodes"
            :key="node.id"
            :label="node.title || '未命名'"
            :value="node.id"
          />
        </el-select>
      </div>

      <!-- Output area -->
      <div v-if="outputText || isStreaming" class="output-section">
        <div class="output-header">
          <span class="output-label">执行结果</span>
          <el-button v-if="isStreaming" text size="small" type="danger" @click="stopStreaming">停止</el-button>
        </div>
        <div class="output-area" ref="outputEl">
          <p class="output-text">{{ outputText }}<span v-if="isStreaming" class="cursor">▍</span></p>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="emit('update:visible', false)" :disabled="isStreaming">取消</el-button>
      <el-button
        type="primary"
        :loading="isStreaming"
        :disabled="!instruction.trim()"
        @click="handleSubmit"
      >
        {{ isStreaming ? '执行中...' : '执行指令' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { streamGlobalDirective } from '@/api/drama'
import type { ScriptNode } from '@/api/drama'

const props = defineProps<{
  visible: boolean
  projectId: number
  nodes: ScriptNode[]
}>()

const emit = defineEmits<{
  (e: 'update:visible', val: boolean): void
}>()

const instruction = ref('')
const scope = ref<'outline' | 'all_nodes' | 'selected_nodes'>('all_nodes')
const selectedNodeIds = ref<number[]>([])
const outputText = ref('')
const isStreaming = ref(false)
const outputEl = ref<HTMLElement>()

let abortController: AbortController | null = null

// Flatten tree nodes for selector
const flatNodes = computed(() => {
  const result: ScriptNode[] = []
  function walk(nodes: ScriptNode[]) {
    for (const n of nodes) {
      result.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(props.nodes)
  return result
})

async function scrollOutput() {
  await nextTick()
  if (outputEl.value) outputEl.value.scrollTop = outputEl.value.scrollHeight
}

function stopStreaming() {
  abortController?.abort()
  isStreaming.value = false
}

async function handleSubmit() {
  if (!instruction.value.trim()) return
  if (scope.value === 'selected_nodes' && !selectedNodeIds.value.length) {
    ElMessage.warning('请选择至少一个节点')
    return
  }

  outputText.value = ''
  isStreaming.value = true

  const data: { directive: string; scope?: string; node_ids?: number[] } = {
    directive: instruction.value,
    scope: scope.value,
  }
  if (scope.value === 'selected_nodes') {
    data.node_ids = selectedNodeIds.value
  }

  abortController = streamGlobalDirective(
    props.projectId,
    data,
    (chunk) => {
      outputText.value += chunk
      scrollOutput()
    },
    () => {
      isStreaming.value = false
      ElMessage.success('指令执行完成')
    },
    (error) => {
      isStreaming.value = false
      ElMessage.error('执行失败：' + error)
    },
  )
}

function resetForm() {
  instruction.value = ''
  scope.value = 'all_nodes'
  selectedNodeIds.value = []
  outputText.value = ''
  isStreaming.value = false
}
</script>

<style scoped>
.directive-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
}

.scope-radios {
  display: flex;
  gap: 16px;
}

.output-section {
  background: #F7F6F3;
  border: 1px solid #E0DFDC;
  border-radius: 10px;
  overflow: hidden;
}

.output-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #E0DFDC;
  background: white;
}

.output-label {
  font-size: 12px;
  font-weight: 600;
  color: #7A7A7A;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.output-area {
  max-height: 200px;
  overflow-y: auto;
  padding: 12px 14px;
}

.output-text {
  font-size: 13px;
  line-height: 1.8;
  color: #2C2C2C;
  white-space: pre-wrap;
  margin: 0;
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
</style>
