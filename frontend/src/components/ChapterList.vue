<template>
  <div class="chapter-list">
    <!-- 列表头部 -->
    <div class="list-header">
      <span class="list-title">章节目录</span>
      <el-button
        size="small"
        type="primary"
        :icon="Plus"
        circle
        @click="showCreateDialog = true"
        title="新建章节"
      />
    </div>

    <!-- 章节列表 -->
    <div class="chapters-scroll">
      <div v-if="chapters.length === 0" class="empty-chapters">
        <p>暂无章节</p>
        <el-button size="small" text @click="showCreateDialog = true">+ 添加第一章</el-button>
      </div>

      <div
        v-for="chapter in chapters"
        :key="chapter.id"
        class="chapter-item"
        :class="{ active: currentChapter?.id === chapter.id }"
        @click="selectChapter(chapter)"
        @dblclick="startRename(chapter)"
      >
        <!-- 重命名输入框 -->
        <el-input
          v-if="renamingId === chapter.id"
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
            <span class="word-count">{{ chapter.word_count.toLocaleString() }} 字</span>
            <!-- 删除按钮，悬停显示 -->
            <el-button
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

    <!-- 新建章节对话框 -->
    <el-dialog
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
import { ref, computed, nextTick } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import { useChapterStore } from '@/stores/chapter'
import type { Chapter } from '@/api/chapter'

// 接收项目 ID
const props = defineProps<{
  projectId: number
}>()

const chapterStore = useChapterStore()

// 从 store 获取响应式数据
const chapters = computed(() => chapterStore.chapters)
const currentChapter = computed(() => chapterStore.currentChapter)

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
  renameInputRef.value?.[0]?.focus()
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
  color: #57534e;
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
  color: #a8a29e;
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
  background-color: rgba(102, 126, 234, 0.04);
}

.chapter-item.active {
  background-color: rgba(102, 126, 234, 0.08);
  border-left-color: #667eea;
}

.chapter-info {
  flex: 1;
  min-width: 0;
  margin-right: 8px;
}

.chapter-order {
  display: block;
  font-size: 11px;
  color: #a8a29e;
  margin-bottom: 2px;
}

.chapter-title {
  display: block;
  font-size: 13px;
  color: #1c1917;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chapter-item.active .chapter-title {
  color: #667eea;
  font-weight: 500;
}

.chapter-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.word-count {
  font-size: 11px;
  color: #a8a29e;
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

.rename-input {
  width: 100%;
}
</style>
