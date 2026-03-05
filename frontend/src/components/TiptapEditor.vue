<template>
  <div class="tiptap-wrapper">
    <!-- 编辑器主体 -->
    <div class="editor-container">
      <editor-content :editor="editor" class="editor-content" />
    </div>

    <!-- 底部状态栏 -->
    <div class="editor-statusbar">
      <span class="saving-indicator" v-if="saving">
        <el-icon class="rotating"><Loading /></el-icon>
        保存中...
      </span>
      <span class="saved-indicator" v-else-if="lastSaved">
        <el-icon><Check /></el-icon>
        已保存
      </span>
      <span class="word-count-display">
        <el-icon><Document /></el-icon>
        {{ charCount }} 字
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import { Loading, Check, Document } from '@element-plus/icons-vue'

// Props 和 Emits
const props = defineProps<{
  modelValue: string   // 章节纯文本内容
  saving: boolean      // 保存中状态（由父组件传入）
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [value: string]
}>()

// 上次保存时间（本地显示用）
const lastSaved = ref(false)

// 防抖定时器
let debounceTimer: ReturnType<typeof setTimeout> | null = null

// 初始化 Tiptap 编辑器
const editor = useEditor({
  content: props.modelValue || '',
  extensions: [
    StarterKit,
    Placeholder.configure({
      placeholder: '开始创作你的故事...',
    }),
    CharacterCount,
  ],
  editorProps: {
    attributes: {
      class: 'prose-editor',
    },
  },
  onUpdate({ editor }) {
    // 获取纯文本内容
    const text = editor.getText()
    emit('update:modelValue', text)

    // 防抖 2 秒后触发自动保存
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      emit('change', text)
      lastSaved.value = true
    }, 2000)
  },
})

// 从字符统计扩展获取字数
const charCount = computed(() => {
  return editor.value?.storage.characterCount.characters() ?? 0
})

// 监听外部 modelValue 变化（切换章节时更新编辑器内容）
watch(
  () => props.modelValue,
  (newVal) => {
    if (!editor.value) return
    const currentText = editor.value.getText()
    // 只有内容真正不同时才更新（避免光标跳动）
    if (newVal !== currentText) {
      editor.value.commands.setContent(newVal || '', false)
      lastSaved.value = false
    }
  }
)

// 组件卸载时清理
onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  editor.value?.destroy()
})
</script>

<style scoped>
.tiptap-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f8f6f0;
}

/* 编辑器容器 */
.editor-container {
  flex: 1;
  overflow-y: auto;
  padding: 48px 64px;
}

/* 编辑器内容区域 */
:deep(.editor-content) {
  height: 100%;
}

:deep(.ProseMirror) {
  min-height: 100%;
  outline: none;
  font-family: 'Noto Serif SC', serif;
  font-size: 17px;
  line-height: 2;
  color: #2c2c2c;
  caret-color: #e2b714;
  max-width: 720px;
  margin: 0 auto;
}

:deep(.ProseMirror p) {
  margin-bottom: 1.2em;
  text-indent: 2em;
}

:deep(.ProseMirror p.is-editor-empty:first-child::before) {
  content: attr(data-placeholder);
  float: left;
  color: #b0a898;
  pointer-events: none;
  height: 0;
}

/* 标题样式 */
:deep(.ProseMirror h1),
:deep(.ProseMirror h2),
:deep(.ProseMirror h3) {
  font-weight: 700;
  color: #1a1a2e;
  text-indent: 0;
  margin: 1.5em 0 0.8em;
}

/* 引用样式 */
:deep(.ProseMirror blockquote) {
  border-left: 3px solid #e2b714;
  padding-left: 16px;
  color: #666;
  font-style: italic;
}

/* 代码样式 */
:deep(.ProseMirror code) {
  background: #f0ede6;
  padding: 2px 4px;
  border-radius: 3px;
  font-family: monospace;
}

/* 底部状态栏 */
.editor-statusbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 24px;
  background-color: #f0ede6;
  border-top: 1px solid #ddd8ce;
  font-size: 12px;
  color: #8a8070;
}

.saving-indicator,
.saved-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #b0a898;
}

.saved-indicator {
  color: #7abf7a;
}

.word-count-display {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

/* 旋转动画（保存中图标） */
.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
