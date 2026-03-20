<template>
  <div class="chapter-list">
    <!-- 列表头部 -->
    <div class="list-header">
      <span class="list-title">章节目录</span>
      <div class="header-actions">
        <el-button
          v-if="!batchMode && chapters.length > 0"
          size="small"
          text
          type="info"
          @click="enterBatchMode"
          title="批量管理"
        >
          批量
        </el-button>
        <el-button
          size="small"
          type="primary"
          :icon="Plus"
          circle
          @click="showCreateDialog = true"
          title="新建章节"
        />
      </div>
    </div>

    <!-- 批量操作栏 -->
    <div v-if="batchMode" class="batch-bar">
      <el-checkbox
        :model-value="isAllSelected"
        :indeterminate="isIndeterminate"
        @change="toggleSelectAll"
      >
        全选
      </el-checkbox>
      <span class="batch-info">已选 {{ selectedIds.size }} 项</span>
      <div class="batch-actions">
        <el-button size="small" type="danger" :disabled="selectedIds.size === 0" @click="handleBatchDelete">
          删除
        </el-button>
        <el-button size="small" @click="exitBatchMode">取消</el-button>
      </div>
    </div>

    <!-- 章节列表 -->
    <div class="chapters-scroll" v-bind="containerProps">
      <div v-if="chapters.length === 0" class="empty-chapters">
        <p>暂无章节</p>
        <el-button size="small" text @click="showCreateDialog = true">+ 添加第一章</el-button>
      </div>

      <div v-else v-bind="wrapperProps">
        <div
          v-for="{ data: chapter, index } in virtualList"
          :key="chapter.id"
          :data-id="chapter.id"
          class="chapter-item"
          :class="{
            active: !batchMode && currentChapter?.id === chapter.id,
            selected: batchMode && selectedIds.has(chapter.id),
          }"
          @click="batchMode ? toggleSelect(chapter.id) : selectChapter(chapter)"
          @dblclick="batchMode ? undefined : startRename(chapter)"
        >
        <!-- 批量模式：复选框 -->
        <el-checkbox
          v-if="batchMode"
          :model-value="selectedIds.has(chapter.id)"
          @change="toggleSelect(chapter.id)"
          @click.stop
          class="batch-checkbox"
        />

        <!-- 重命名输入框 -->
        <el-input
          v-if="!batchMode && renamingId === chapter.id"
          v-model="renameValue"
          size="small"
          class="rename-input"
          @blur="submitRename(chapter)"
          @keyup.enter="submitRename(chapter)"
          @keyup.esc="cancelRename"
          @click.stop
          ref="renameInputRef"
        />

        <!-- 正常显示 -->
        <template v-else>
          <div class="chapter-info">
            <span class="chapter-order">第 {{ chapter.sort_order }} 章</span>
            <span class="chapter-title">{{ chapter.title }}</span>
          </div>
          <div class="chapter-meta">
            <span class="chapter-status" :class="chapter.word_count > 0 ? 'has-content' : ''">
              {{ chapter.word_count > 0 ? '已写' : '空' }}
            </span>
            <span class="word-count">{{ chapter.word_count.toLocaleString() }} 字</span>
            <!-- 上移/下移按钮，悬停显示 -->
            <div v-if="!batchMode" class="move-btns">
              <el-button
                class="move-btn"
                size="small"
                text
                :icon="Top"
                :disabled="index === 0"
                @click.stop="handleMoveUp(index)"
              />
              <el-button
                class="move-btn"
                size="small"
                text
                :icon="Bottom"
                :disabled="index === chapters.length - 1"
                @click.stop="handleMoveDown(index)"
              />
            </div>
            <!-- AI生成标题按钮，悬停显示 -->
            <el-tooltip content="AI 生成标题" placement="top" v-if="!batchMode">
              <el-button
                class="ai-title-btn"
                size="small"
                text
                type="warning"
                :icon="MagicStick"
                :loading="generatingTitleId === chapter.id"
                @click.stop="handleGenerateTitle(chapter)"
              />
            </el-tooltip>
            <!-- 删除按钮，悬停显示（非批量模式） -->
            <el-button
              v-if="!batchMode"
              class="delete-btn"
              size="small"
              text
              type="danger"
              :icon="Delete"
              @click.stop="handleDelete(chapter)"
            />
          </div>
        </template>
        </div>
      </div>
    </div>

    <!-- 新建章节对话框 -->
    <el-dialog
      :close-on-press-escape="false"
      v-model="showCreateDialog"
      title="新建章节"
      width="400px"
      append-to-body
    >
      <el-form @submit.prevent="handleCreate">
        <el-form-item label="章节标题">
          <el-input
            v-model="newChapterTitle"
            placeholder="请输入章节标题"
            maxlength="100"
            autofocus
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Delete, MagicStick, Top, Bottom } from '@element-plus/icons-vue'
import { useVirtualList } from '@vueuse/core'
import { useChapterStore } from '@/stores/chapter'
import { reorderChapters } from '@/api/chapter'
import type { Chapter } from '@/api/chapter'
import { streamGenerate } from '@/api/ai'

// 接收项目 ID
const props = defineProps<{
  projectId: number
}>()

const chapterStore = useChapterStore()

// 从 store 获取响应式数据
const chapters = computed(() => chapterStore.chapters)
const currentChapter = computed(() => chapterStore.currentChapter)

// 虚拟滚动配置
const { list: virtualList, containerProps, wrapperProps, scrollTo } = useVirtualList(chapters, {
  itemHeight: 52, // 章节条目高度
  overscan: 5, // 预渲染数量
})

// 监听当前章节变化，自动滚动到可见区域
watch(() => chapterStore.currentChapter, (chapter) => {
  if (chapter) {
    const index = chapters.value.findIndex(c => c.id === chapter.id)
    if (index > -1) {
      scrollTo(index)
    }
  }
})

// 新建章节状态
const showCreateDialog = ref(false)
const newChapterTitle = ref('')
const creating = ref(false)

// 重命名状态
const renamingId = ref<number | null>(null)
const renameValue = ref('')
const renameInputRef = ref()

// 选中章节
function selectChapter(chapter: Chapter) {
  chapterStore.setCurrentChapter(chapter)
}

// 创建新章节
async function handleCreate() {
  if (!newChapterTitle.value.trim()) return
  creating.value = true
  try {
    const chapter = await chapterStore.createNewChapter(props.projectId, {
      title: newChapterTitle.value.trim(),
    })
    showCreateDialog.value = false
    newChapterTitle.value = ''
    // 自动跳转到新章节
    chapterStore.setCurrentChapter(chapter)
  } finally {
    creating.value = false
  }
}

// 开始重命名（双击触发）
async function startRename(chapter: Chapter) {
  renamingId.value = chapter.id
  renameValue.value = chapter.title
  // 等待输入框渲染后聚焦
  await nextTick()
  // v-for 中的 ref 在条件渲染时可能是单个元素或数组
  const input = Array.isArray(renameInputRef.value)
    ? renameInputRef.value[0]
    : renameInputRef.value
  input?.focus()
}

// 提交重命名
async function submitRename(chapter: Chapter) {
  if (!renameValue.value.trim() || renameValue.value === chapter.title) {
    cancelRename()
    return
  }
  await chapterStore.updateCurrentChapter(props.projectId, chapter.id, {
    title: renameValue.value.trim(),
  })
  cancelRename()
}

// 取消重命名
function cancelRename() {
  renamingId.value = null
  renameValue.value = ''
}

// 删除章节确认
async function handleDelete(chapter: Chapter) {
  await ElMessageBox.confirm(`确定要删除《${chapter.title}》吗？`, '删除确认', {
    type: 'warning',
    confirmButtonText: '确认删除',
    cancelButtonText: '取消',
  })
  await chapterStore.removeChapter(props.projectId, chapter.id)
}

// ========== AI 生成章节标题 ==========
const generatingTitleId = ref<number | null>(null)

async function handleGenerateTitle(chapter: Chapter) {
  if (!chapter.content || chapter.word_count === 0) {
    ElMessage.warning('章节内容为空，无法生成标题')
    return
  }

  generatingTitleId.value = chapter.id
  let result = ''

  streamGenerate(
    props.projectId,
    {
      action: 'generate_title',
      content: chapter.content,
      chapter_id: chapter.id,
    },
    (text) => {
      result += text
    },
    async () => {
      generatingTitleId.value = null
      const newTitle = result.trim().replace(/^["'《「]+|["'》」]+$/g, '')
      if (newTitle) {
        await chapterStore.updateCurrentChapter(props.projectId, chapter.id, {
          title: newTitle,
        })
        ElMessage.success(`标题已更新为「${newTitle}」`)
      }
    },
    (error) => {
      generatingTitleId.value = null
      ElMessage.error(`生成标题失败: ${error}`)
    }
  )
}

// ========== 批量操作 ==========
const batchMode = ref(false)
const selectedIds = reactive(new Set<number>())

const isAllSelected = computed(() => chapters.value.length > 0 && selectedIds.size === chapters.value.length)
const isIndeterminate = computed(() => selectedIds.size > 0 && selectedIds.size < chapters.value.length)

function enterBatchMode() {
  batchMode.value = true
  selectedIds.clear()
}

function exitBatchMode() {
  batchMode.value = false
  selectedIds.clear()
}

function toggleSelect(id: number) {
  if (selectedIds.has(id)) {
    selectedIds.delete(id)
  } else {
    selectedIds.add(id)
  }
}

function toggleSelectAll(checked: unknown) {
  if (checked) {
    chapters.value.forEach((c) => selectedIds.add(c.id))
  } else {
    selectedIds.clear()
  }
}

async function handleBatchDelete() {
  const count = selectedIds.size
  await ElMessageBox.confirm(`确定要删除选中的 ${count} 个章节吗？此操作不可恢复。`, '批量删除确认', {
    type: 'warning',
    confirmButtonText: `删除 ${count} 章`,
    cancelButtonText: '取消',
  })
  await chapterStore.removeChapters(props.projectId, Array.from(selectedIds))
  ElMessage.success(`已删除 ${count} 个章节`)
  exitBatchMode()
}

// ========== 上下移动排序 ==========
async function handleMoveUp(index: number) {
  if (index <= 0) return
  await swapChapters(index, index - 1)
}

async function handleMoveDown(index: number) {
  if (index >= chapters.value.length - 1) return
  await swapChapters(index, index + 1)
}

async function swapChapters(fromIndex: number, toIndex: number) {
  const chA = chapters.value[fromIndex]
  const chB = chapters.value[toIndex]
  if (!chA || !chB) return

  // 交换 sort_order
  const orders = [
    { id: chA.id, sort_order: chB.sort_order },
    { id: chB.id, sort_order: chA.sort_order },
  ]

  try {
    await reorderChapters(props.projectId, orders)
    await chapterStore.fetchChapters(props.projectId)
  } catch {
    ElMessage.error('排序失败，请重试')
  }
}
</script>

<style scoped>
.chapter-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: white;
}

/* 列表头部 */
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #f0ede6;
}

.list-title {
  font-size: 14px;
  font-weight: 600;
  color: #5C5C5C;
  letter-spacing: 0.5px;
}

/* 章节滚动区 */
.chapters-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.empty-chapters {
  text-align: center;
  padding: 32px 16px;
  color: #9E9E9E;
  font-size: 13px;
}

/* 章节条目 */
.chapter-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: background-color 0.15s;
  border-left: 3px solid transparent;
}

.chapter-item:hover {
  background-color: rgba(107, 123, 141, 0.04);
}

.chapter-item.active {
  background-color: rgba(107, 123, 141, 0.08);
  border-left-color: #6B7B8D;
}

.chapter-info {
  flex: 1;
  min-width: 0;
  margin-right: 8px;
}

.chapter-order {
  display: block;
  font-size: 11px;
  color: #9E9E9E;
  margin-bottom: 2px;
}

.chapter-title {
  display: block;
  font-size: 13px;
  color: #2C2C2C;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chapter-item.active .chapter-title {
  color: #6B7B8D;
  font-weight: 500;
}

.chapter-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.chapter-status {
  font-size: 10px;
  color: #9E9E9E;
  padding: 1px 4px;
  border-radius: 3px;
  background: #F0EFEC;
}

.chapter-status.has-content {
  color: #7abf7a;
  background: rgba(122, 191, 122, 0.1);
}

.word-count {
  font-size: 11px;
  color: #9E9E9E;
}

/* AI生成标题按钮：默认隐藏，悬停显示 */
.ai-title-btn {
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px;
}

.chapter-item:hover .ai-title-btn {
  opacity: 1;
}

/* 删除按钮：默认隐藏，悬停显示 */
.delete-btn {
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px;
}

.chapter-item:hover .delete-btn {
  opacity: 1;
}

/* 头部操作按钮组 */
.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

/* 批量操作栏 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: #fef9ef;
  border-bottom: 1px solid #f0ede6;
  font-size: 13px;
}

.batch-info {
  color: #9E9E9E;
  font-size: 12px;
}

.batch-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}

/* 批量复选框 */
.batch-checkbox {
  margin-right: 8px;
  flex-shrink: 0;
}

/* 批量选中状态 */
.chapter-item.selected {
  background-color: rgba(107, 123, 141, 0.08);
}

.rename-input {
  width: 100%;
}

/* 上下移动按钮 */
.move-btns {
  display: flex;
  flex-direction: column;
  gap: 0;
  opacity: 0;
  transition: opacity 0.15s;
}

.chapter-item:hover .move-btns {
  opacity: 1;
}

.move-btn {
  padding: 0 2px;
  height: 16px;
}
</style>
