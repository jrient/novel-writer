<template>
  <div class="tiptap-wrapper" :class="{ 'fullscreen': isFullscreen }">
    <!-- 格式工具栏 -->
    <div class="editor-toolbar" v-if="editor">
      <div class="toolbar-group">
        <el-tooltip content="加粗 (Ctrl+B)" placement="bottom">
          <button
            class="toolbar-btn"
            :class="{ active: editor.isActive('bold') }"
            @click="editor.chain().focus().toggleBold().run()"
          >B</button>
        </el-tooltip>
        <el-tooltip content="斜体 (Ctrl+I)" placement="bottom">
          <button
            class="toolbar-btn italic"
            :class="{ active: editor.isActive('italic') }"
            @click="editor.chain().focus().toggleItalic().run()"
          ><em>I</em></button>
        </el-tooltip>
        <el-tooltip content="删除线" placement="bottom">
          <button
            class="toolbar-btn strike"
            :class="{ active: editor.isActive('strike') }"
            @click="editor.chain().focus().toggleStrike().run()"
          ><s>S</s></button>
        </el-tooltip>
      </div>

      <div class="toolbar-divider" />

      <div class="toolbar-group">
        <el-tooltip content="标题 1" placement="bottom">
          <button
            class="toolbar-btn"
            :class="{ active: editor.isActive('heading', { level: 1 }) }"
            @click="editor.chain().focus().toggleHeading({ level: 1 }).run()"
          >H1</button>
        </el-tooltip>
        <el-tooltip content="标题 2" placement="bottom">
          <button
            class="toolbar-btn"
            :class="{ active: editor.isActive('heading', { level: 2 }) }"
            @click="editor.chain().focus().toggleHeading({ level: 2 }).run()"
          >H2</button>
        </el-tooltip>
        <el-tooltip content="标题 3" placement="bottom">
          <button
            class="toolbar-btn"
            :class="{ active: editor.isActive('heading', { level: 3 }) }"
            @click="editor.chain().focus().toggleHeading({ level: 3 }).run()"
          >H3</button>
        </el-tooltip>
      </div>

      <div class="toolbar-divider" />

      <div class="toolbar-group">
        <el-tooltip content="引用" placement="bottom">
          <button
            class="toolbar-btn"
            :class="{ active: editor.isActive('blockquote') }"
            @click="editor.chain().focus().toggleBlockquote().run()"
          >"</button>
        </el-tooltip>
        <el-tooltip content="分隔线" placement="bottom">
          <button
            class="toolbar-btn"
            @click="editor.chain().focus().setHorizontalRule().run()"
          >—</button>
        </el-tooltip>
      </div>

      <div class="toolbar-divider" />

      <div class="toolbar-group">
        <el-tooltip content="撤销 (Ctrl+Z)" placement="bottom">
          <button
            class="toolbar-btn"
            :disabled="!editor.can().undo()"
            @click="editor.chain().focus().undo().run()"
          >
            <el-icon><RefreshLeft /></el-icon>
          </button>
        </el-tooltip>
        <el-tooltip content="重做 (Ctrl+Shift+Z)" placement="bottom">
          <button
            class="toolbar-btn"
            :disabled="!editor.can().redo()"
            @click="editor.chain().focus().redo().run()"
          >
            <el-icon><RefreshRight /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <div class="toolbar-spacer" />

      <!-- 保存按钮 -->
      <div class="toolbar-group">
        <el-tooltip :content="hasUnsavedChanges ? '保存 (Ctrl+S)' : '已保存'" placement="bottom">
          <button
            class="toolbar-btn save-btn"
            :class="{ 'unsaved': hasUnsavedChanges, 'saved': !hasUnsavedChanges && !saving }"
            @click="handleSave"
            :disabled="saving"
          >
            <el-icon v-if="saving" class="rotating"><Loading /></el-icon>
            <el-icon v-else-if="hasUnsavedChanges"><Document /></el-icon>
            <el-icon v-else><Check /></el-icon>
          </button>
        </el-tooltip>
      </div>

      <div class="toolbar-divider" />

      <div class="toolbar-group">
        <el-tooltip :content="isFullscreen ? '退出专注 (Esc)' : '专注模式'" placement="bottom">
          <button class="toolbar-btn focus-btn" @click="toggleFullscreen">
            <el-icon><FullScreen v-if="!isFullscreen" /><Close v-else /></el-icon>
          </button>
        </el-tooltip>
      </div>
    </div>

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
      <span class="saved-indicator" v-else-if="!hasUnsavedChanges">
        <el-icon><Check /></el-icon>
        已保存
      </span>
      <span class="unsaved-indicator" v-else>
        <el-icon><WarningFilled /></el-icon>
        未保存
      </span>
      <div class="statusbar-right">
        <span class="word-count-display">
          <el-icon><Document /></el-icon>
          {{ charCount }} 字
        </span>
        <span class="paragraph-count" v-if="paragraphCount > 0">
          {{ paragraphCount }} 段
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onBeforeUnmount, computed, onMounted, onUnmounted } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import CharacterCount from '@tiptap/extension-character-count'
import {
  Loading, Check, Document, RefreshLeft, RefreshRight,
  FullScreen, Close, WarningFilled,
} from '@element-plus/icons-vue'

const props = defineProps<{
  modelValue: string
  saving: boolean
  hasUnsavedChanges?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
  'change': [value: string]
  'save': [value: string]
}>()

const lastSaved = ref(false)
const isFullscreen = ref(false)
const internalUnsaved = ref(false)
let debounceTimer: ReturnType<typeof setTimeout> | null = null
let savedHideTimer: ReturnType<typeof setTimeout> | null = null

// 计算是否有未保存的更改（优先使用外部传入的状态）
const hasUnsavedChanges = computed(() => {
  return props.hasUnsavedChanges !== undefined ? props.hasUnsavedChanges : internalUnsaved.value
})

// 纯文本转 HTML：将换行分隔的段落转为 <p> 标签
function textToHtml(text: string): string {
  if (!text) return ''
  // 如果已经是 HTML 格式，直接返回
  if (text.startsWith('<p>') || text.startsWith('<h')) return text
  return text
    .split(/\n/)
    .map(line => `<p>${line || '<br>'}</p>`)
    .join('')
}

// HTML 转纯文本：保留换行结构
function htmlToText(html: string): string {
  if (!html) return ''
  const div = document.createElement('div')
  div.innerHTML = html
  // 每个 <p> 块用换行分隔
  const paragraphs = div.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li')
  if (paragraphs.length === 0) return div.textContent || ''
  return Array.from(paragraphs)
    .map(p => p.textContent || '')
    .join('\n')
}

const editor = useEditor({
  content: textToHtml(props.modelValue || ''),
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
    const html = editor.getHTML()
    const text = htmlToText(html)
    emit('update:modelValue', text)
    internalUnsaved.value = true
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      emit('change', text)
      internalUnsaved.value = false
      lastSaved.value = true
      // 3秒后隐藏保存提示
      if (savedHideTimer) clearTimeout(savedHideTimer)
      savedHideTimer = setTimeout(() => {
        lastSaved.value = false
      }, 3000)
    }, 1000)
  },
})

const charCount = computed(() => {
  return editor.value?.storage.characterCount.characters() ?? 0
})

const paragraphCount = computed(() => {
  if (!editor.value) return 0
  const text = editor.value.getText()
  return text.split(/\n+/).filter(p => p.trim().length > 0).length
})

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
}

// 手动保存
function handleSave() {
  if (!editor.value || props.saving) return
  const html = editor.value.getHTML()
  const text = htmlToText(html)
  if (debounceTimer) clearTimeout(debounceTimer)
  emit('save', text)
  internalUnsaved.value = false
  lastSaved.value = true
  if (savedHideTimer) clearTimeout(savedHideTimer)
  savedHideTimer = setTimeout(() => {
    lastSaved.value = false
  }, 3000)
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && isFullscreen.value) {
    isFullscreen.value = false
  }
  // Ctrl+S / Cmd+S 立即保存
  if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    handleSave()
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
})

watch(
  () => props.modelValue,
  (newVal) => {
    if (!editor.value) return
    const currentHtml = editor.value.getHTML()
    const currentText = htmlToText(currentHtml)
    if (newVal !== currentText) {
      editor.value.commands.setContent(textToHtml(newVal || ''), false)
      // 外部更新内容时，重置未保存状态
      internalUnsaved.value = false
    }
  }
)

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (savedHideTimer) clearTimeout(savedHideTimer)
  editor.value?.destroy()
})
</script>

<style scoped>
.tiptap-wrapper {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #F7F6F3;
}

/* 全屏专注模式 */
.tiptap-wrapper.fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2000;
  background-color: #F7F6F3;
}

.tiptap-wrapper.fullscreen .editor-container {
  padding: 48px 120px;
}

.tiptap-wrapper.fullscreen .editor-toolbar {
  justify-content: center;
}

/* 格式工具栏 */
.editor-toolbar {
  display: flex;
  align-items: center;
  padding: 6px 16px;
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  gap: 2px;
  flex-shrink: 0;
}

.toolbar-group {
  display: flex;
  gap: 2px;
}

.toolbar-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 28px;
  border: none;
  background: transparent;
  color: #7A7A7A;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  font-weight: 600;
  transition: all 0.15s;
}

.toolbar-btn:hover {
  background-color: #F0EFEC;
  color: #2C2C2C;
}

.toolbar-btn.active {
  background: linear-gradient(135deg, #6B7B8D 0%, #5A6B7A 100%);
  color: white;
}

.toolbar-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.toolbar-btn.italic {
  font-style: italic;
}

.toolbar-btn.strike {
  text-decoration: line-through;
}

.toolbar-divider {
  width: 1px;
  height: 20px;
  background-color: #E0DFDC;
  margin: 0 6px;
}

.toolbar-spacer {
  flex: 1;
}

.focus-btn {
  color: #9E9E9E;
}

.focus-btn:hover {
  color: #6B7B8D;
  background-color: rgba(107, 123, 141, 0.08);
}

/* 保存按钮样式 */
.save-btn {
  width: auto;
  padding: 0 10px;
  gap: 4px;
}

.save-btn.unsaved {
  color: #f56c6c;
  background-color: rgba(245, 108, 108, 0.1);
}

.save-btn.unsaved:hover {
  background-color: rgba(245, 108, 108, 0.15);
}

.save-btn.saved {
  color: #67c23a;
  background-color: rgba(103, 194, 58, 0.1);
}

.save-btn.saved:hover {
  background-color: rgba(103, 194, 58, 0.15);
}

/* 编辑器容器 */
.editor-container {
  flex: 1;
  overflow-y: auto;
  padding: 48px 64px;
}

:deep(.editor-content) {
  height: 100%;
}

:deep(.ProseMirror) {
  min-height: 100%;
  outline: none;
  font-family: 'Noto Serif SC', serif;
  font-size: 17px;
  line-height: 2;
  color: #2C2C2C;
  caret-color: #6B7B8D;
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

:deep(.ProseMirror h1),
:deep(.ProseMirror h2),
:deep(.ProseMirror h3) {
  font-weight: 700;
  color: #2C2C2C;
  text-indent: 0;
  margin: 1.5em 0 0.8em;
}

:deep(.ProseMirror h1) { font-size: 1.6em; }
:deep(.ProseMirror h2) { font-size: 1.35em; }
:deep(.ProseMirror h3) { font-size: 1.15em; }

:deep(.ProseMirror blockquote) {
  border-left: 3px solid #6B7B8D;
  padding-left: 16px;
  color: #7A7A7A;
  font-style: italic;
}

:deep(.ProseMirror hr) {
  border: none;
  border-top: 1px solid #E0DFDC;
  margin: 2em 0;
}

:deep(.ProseMirror code) {
  background: #F0EFEC;
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
  background-color: white;
  border-top: 1px solid #E0DFDC;
  font-size: 12px;
  color: #9E9E9E;
  flex-shrink: 0;
}

.statusbar-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.saving-indicator,
.saved-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #9E9E9E;
}

.saved-indicator {
  color: #7abf7a;
}

.unsaved-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #f56c6c;
}

.word-count-display,
.paragraph-count {
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}

.paragraph-count {
  color: #d6d3d1;
}

.rotating {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
