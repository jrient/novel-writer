<template>
  <div class="workbench-page">
    <!-- Header -->
    <header class="workbench-header">
      <div class="header-left">
        <el-button text :icon="ArrowLeft" @click="router.push('/drama')">返回</el-button>
        <el-divider direction="vertical" />
        <el-button text @click="router.push(`/drama/wizard/${dramaStore.currentProject?.id}`)">剧本引导</el-button>
        <span class="project-title">{{ dramaStore.currentProject?.title || '加载中...' }}</span>
        <el-tag
          v-if="dramaStore.currentProject"
          :type="dramaStore.currentProject.script_type === 'explanatory' ? 'success' : 'primary'"
          size="small"
          effect="light"
        >
          {{ dramaStore.currentProject.script_type === 'explanatory' ? '解说漫' : '动态漫' }}
        </el-tag>
      </div>

      <div class="header-right">
        <el-button
          size="small"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': showSettingsDrawer }"
          @click="showSettingsDrawer = !showSettingsDrawer"
        >
          <el-icon><Setting /></el-icon>
          设定
        </el-button>

        <el-button size="small" class="toolbar-btn" @click="showDirectiveDialog = true">
          <el-icon><MagicStick /></el-icon>
          全局指令
        </el-button>

        <el-dropdown trigger="click" @command="handleExport">
          <el-button size="small" class="toolbar-btn">
            <el-icon><Download /></el-icon>
            导出
            <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="txt">导出 TXT</el-dropdown-item>
              <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>

        <el-button size="small" class="toolbar-btn" @click="showAiConfig = true">
          <el-icon><Setting /></el-icon>
          AI 配置
        </el-button>

        <el-button
          size="small"
          class="toolbar-btn"
          :class="{ 'toolbar-btn--active': showAiPanel }"
          @click="showAiPanel = !showAiPanel"
        >
          <el-icon><Cpu /></el-icon>
          AI 助手
        </el-button>
      </div>
    </header>

    <!-- Main three-column layout -->
    <div class="workbench-main">
      <!-- Left: outline tree -->
      <aside class="sidebar-left" :style="{ width: leftWidth + 'px' }">
        <ScriptOutlineTree
          :nodes="dramaStore.nodes"
          :script-type="dramaStore.currentProject?.script_type || 'dynamic'"
          :current-node-id="dramaStore.currentNode?.id ?? null"
          @select-node="handleSelectNode"
          @add-node="handleAddNode"
          @delete-node="handleDeleteNode"
          @rename-node="handleRenameNode"
        />
      </aside>

      <!-- Resizer left -->
      <div class="resizer" @mousedown="startResizeLeft" />

      <!-- Center: editor -->
      <main class="editor-column">
        <ScriptEditor
          :node="dramaStore.currentNode"
          :script-type="dramaStore.currentProject?.script_type || 'dynamic'"
          :project-id="projectId"
          @save="handleSaveNode"
          @version-restored="handleVersionRestored"
        />
      </main>

      <!-- Resizer right (only when panel open) -->
      <template v-if="showAiPanel">
        <div class="resizer" @mousedown="startResizeRight" />
        <!-- Right: AI panel -->
        <aside class="sidebar-right" :style="{ width: rightWidth + 'px' }">
          <ScriptAiPanel
            :project-id="projectId"
            :node="dramaStore.currentNode"
            :script-type="dramaStore.currentProject?.script_type || 'dynamic'"
            @toggle="showAiPanel = false"
            @apply="handleApplyAiText"
          />
        </aside>
      </template>
    </div>

    <!-- Footer stats bar -->
    <footer class="workbench-footer">
      <span class="footer-stat">
        节点总数：{{ dramaStore.nodes.length }}
      </span>
      <span class="footer-stat">
        已完成：{{ completedCount }} / {{ dramaStore.nodes.length }}
      </span>
      <span v-if="dramaStore.currentNode" class="footer-stat footer-stat--current">
        当前：{{ dramaStore.currentNode.title || '未命名' }}
        <el-tag size="small" effect="plain" style="margin-left: 6px">
          {{ nodeTypeLabel(dramaStore.currentNode.node_type) }}
        </el-tag>
      </span>
    </footer>

    <!-- Dialogs & Drawers -->
    <GlobalDirectiveDialog
      v-model:visible="showDirectiveDialog"
      :project-id="projectId"
      :nodes="dramaStore.nodes"
    />

    <AiConfigPanel
      v-model:visible="showAiConfig"
      :project="dramaStore.currentProject"
      @saved="dramaStore.fetchProject(projectId)"
    />

    <!-- Settings Drawer -->
    <ScriptSettingsDrawer
      v-model:visible="showSettingsDrawer"
      :settings="dramaStore.projectSettings"
      :project-id="projectId"
      ref="settingsDrawerRef"
      @save="handleSaveSettings"
      @edit-character="handleEditCharacter"
    />

    <!-- Character Edit Overlay -->
    <CharacterEditOverlay
      :visible="showCharacterOverlay"
      :character="editingCharacter"
      @save="handleCharacterSave"
      @cancel="showCharacterOverlay = false"
    />

    <!-- Add node dialog -->
    <el-dialog
      v-model="showAddNodeDialog"
      title="添加节点"
      width="420px"
      :close-on-click-modal="false"
    >
      <div class="add-node-form">
        <div class="form-item">
          <label class="form-label">节点类型</label>
          <el-select v-model="newNode.node_type" style="width: 100%">
            <el-option
              v-for="t in availableNodeTypes"
              :key="t.value"
              :label="t.label"
              :value="t.value"
            />
          </el-select>
        </div>
        <div class="form-item">
          <label class="form-label">节点标题</label>
          <el-input v-model="newNode.title" placeholder="节点标题..." maxlength="100" />
        </div>
      </div>
      <template #footer>
        <el-button @click="showAddNodeDialog = false">取消</el-button>
        <el-button type="primary" :loading="addingNode" @click="confirmAddNode">添加</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ArrowDown, MagicStick, Download, Setting, Cpu,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDramaStore } from '@/stores/drama'
import { getExportUrl } from '@/api/drama'
import { createNodeVersion } from '@/api/drama'
import type { ScriptNode } from '@/api/drama'
import ScriptOutlineTree from '@/components/drama/ScriptOutlineTree.vue'
import ScriptEditor from '@/components/drama/ScriptEditor.vue'
import ScriptAiPanel from '@/components/drama/ScriptAiPanel.vue'
import GlobalDirectiveDialog from '@/components/drama/GlobalDirectiveDialog.vue'
import AiConfigPanel from '@/components/drama/AiConfigPanel.vue'
import ScriptSettingsDrawer from '@/components/drama/ScriptSettingsDrawer.vue'
import CharacterEditOverlay from '@/components/drama/CharacterEditOverlay.vue'
import type { CharacterSetting, ProjectSettings } from '@/api/drama'

const route = useRoute()
const router = useRouter()
const dramaStore = useDramaStore()

const projectId = computed(() => Number(route.params.id))

// Panel visibility
const showAiPanel = ref(true)
const showDirectiveDialog = ref(false)
const showAiConfig = ref(false)

// Settings drawer state
const showSettingsDrawer = ref(false)
const showCharacterOverlay = ref(false)
const editingCharacter = ref<CharacterSetting | null>(null)
const settingsDrawerRef = ref<InstanceType<typeof ScriptSettingsDrawer> | null>(null)

async function handleSaveSettings(settings: ProjectSettings) {
  try {
    await dramaStore.updateProjectSettings(projectId.value, settings)
  } catch (err) {
    console.error('Save settings failed:', err)
    ElMessage.error('设定保存失败')
  }
}

function handleEditCharacter(char: CharacterSetting) {
  editingCharacter.value = char
  showCharacterOverlay.value = true
}

function handleCharacterSave(updated: CharacterSetting) {
  showCharacterOverlay.value = false
  settingsDrawerRef.value?.updateCharacter(updated)
}

// Add node dialog
const showAddNodeDialog = ref(false)
const addingNode = ref(false)
const pendingParentId = ref<number | null>(null)
const newNode = ref({ node_type: 'scene', title: '' })

// Resizable panels
const leftWidth = ref(240)
const rightWidth = ref(320)
const MIN_LEFT = 180
const MAX_LEFT = 380
const MIN_RIGHT = 260
const MAX_RIGHT = 480

let resizingLeft = false
let resizingRight = false
let resizeStartX = 0
let resizeStartWidth = 0

function startResizeLeft(e: MouseEvent) {
  resizingLeft = true
  resizeStartX = e.clientX
  resizeStartWidth = leftWidth.value
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
}

function startResizeRight(e: MouseEvent) {
  resizingRight = true
  resizeStartX = e.clientX
  resizeStartWidth = rightWidth.value
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', stopResize)
}

function onMouseMove(e: MouseEvent) {
  if (resizingLeft) {
    const delta = e.clientX - resizeStartX
    leftWidth.value = Math.max(MIN_LEFT, Math.min(MAX_LEFT, resizeStartWidth + delta))
  } else if (resizingRight) {
    const delta = resizeStartX - e.clientX
    rightWidth.value = Math.max(MIN_RIGHT, Math.min(MAX_RIGHT, resizeStartWidth + delta))
  }
}

function stopResize() {
  resizingLeft = false
  resizingRight = false
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup', stopResize)
}

onUnmounted(stopResize)

// Computed
const completedCount = computed(() => dramaStore.nodes.filter(n => n.is_completed).length)

const nodeTypeLabels: Record<string, string> = {
  episode: '集',
  scene: '场景',
  dialogue: '对白',
  action: '动作',
  effect: '特效',
  inner_voice: '内心独白',
  section: '章节',
  narration: '旁白',
  intro: '介绍',
}

function nodeTypeLabel(type: string) {
  return nodeTypeLabels[type] || type
}

const availableNodeTypes = computed(() => {
  const type = dramaStore.currentProject?.script_type
  if (type === 'explanatory') {
    return [
      { value: 'intro', label: '介绍' },
      { value: 'section', label: '章节' },
      { value: 'narration', label: '旁白' },
    ]
  }
  return [
    { value: 'episode', label: '集' },
    { value: 'scene', label: '场景' },
    { value: 'dialogue', label: '对白' },
    { value: 'action', label: '动作' },
    { value: 'effect', label: '特效' },
    { value: 'inner_voice', label: '内心独白' },
  ]
})

// Track loaded content for dirty checking on node switch
const loadedNodeContent = ref<string | null>(null)

watch(() => dramaStore.currentNode, (node) => {
  loadedNodeContent.value = node?.content ?? null
}, { immediate: true })

// Handlers
async function handleSelectNode(node: ScriptNode) {
  const prev = dramaStore.currentNode
  // Snapshot if switching away from a dirty episode
  if (
    prev &&
    prev.node_type === 'episode' &&
    prev.id !== node.id &&
    prev.content !== loadedNodeContent.value
  ) {
    try {
      await createNodeVersion(projectId.value, prev.id, 'switch')
    } catch {
      // Snapshot failure should not block switch
    }
  }
  dramaStore.selectNode(node)
}

function handleAddNode(parentId: number | null) {
  pendingParentId.value = parentId
  newNode.value = {
    node_type: availableNodeTypes.value[0]?.value || 'scene',
    title: '',
  }
  showAddNodeDialog.value = true
}

async function confirmAddNode() {
  addingNode.value = true
  try {
    const node = await dramaStore.addNode(projectId.value, {
      parent_id: pendingParentId.value,
      node_type: newNode.value.node_type,
      title: newNode.value.title || undefined,
    })
    dramaStore.selectNode(node)
    showAddNodeDialog.value = false
    ElMessage.success('节点已添加')
  } catch {
    ElMessage.error('添加失败')
  } finally {
    addingNode.value = false
  }
}

async function handleDeleteNode(nodeId: number) {
  try {
    await ElMessageBox.confirm('确定删除此节点及其所有子节点？', '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await dramaStore.removeNode(projectId.value, nodeId)
    ElMessage.success('已删除')
  } catch {
    // cancelled
  }
}

async function handleRenameNode(nodeId: number) {
  const node = dramaStore.nodes.find(n => n.id === nodeId)
  if (!node) return
  try {
    const { value } = await ElMessageBox.prompt('输入新名称', '重命名', {
      inputValue: node.title || '',
      confirmButtonText: '确认',
      cancelButtonText: '取消',
    })
    if (value?.trim()) {
      await dramaStore.editNode(projectId.value, nodeId, { title: value.trim() })
    }
  } catch {
    // cancelled
  }
}

async function handleSaveNode(data: {
  title?: string
  content?: string
  speaker?: string
  visual_desc?: string
}) {
  if (!dramaStore.currentNode) return
  try {
    await dramaStore.editNode(projectId.value, dramaStore.currentNode.id, data)
  } catch {
    ElMessage.error('保存失败')
  }
}

function handleApplyAiText(text: string) {
  if (!dramaStore.currentNode) return
  // Snapshot before AI apply (only for episode nodes)
  if (dramaStore.currentNode.node_type === 'episode') {
    createNodeVersion(projectId.value, dramaStore.currentNode.id, 'ai_apply').catch(() => {
      // Snapshot failure should not block apply
    })
  }
  handleSaveNode({ content: text })
}

async function handleVersionRestored() {
  await dramaStore.fetchNodes(projectId.value)
  if (dramaStore.currentNode) {
    const updated = dramaStore.nodes.find(n => n.id === dramaStore.currentNode?.id)
    if (updated) dramaStore.selectNode(updated)
  }
}

async function handleExport(format: 'txt' | 'markdown') {
  try {
    const url = getExportUrl(projectId.value, format)
    const token = localStorage.getItem('access_token')
    const headers: Record<string, string> = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch(url, { headers })
    if (!resp.ok) throw new Error()
    const blob = await resp.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `${dramaStore.currentProject?.title || 'script'}.${format === 'markdown' ? 'md' : 'txt'}`
    a.click()
    URL.revokeObjectURL(a.href)
    ElMessage.success('导出成功')
  } catch {
    ElMessage.error('导出失败')
  }
}

onMounted(async () => {
  try {
    await Promise.all([
      dramaStore.fetchProject(projectId.value),
      dramaStore.fetchNodes(projectId.value),
    ])
    if (dramaStore.nodes.length && !dramaStore.currentNode) {
      dramaStore.selectNode(dramaStore.nodes[0])
    }
    if (dramaStore.currentProject?.title) {
      document.title = `${dramaStore.currentProject.title} - 剧本工作台`
    }
  } catch {
    ElMessage.error('加载失败')
  }
})
</script>

<style scoped>
.workbench-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #F7F6F3;
  overflow: hidden;
}

.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 52px;
  padding: 0 20px;
  background: white;
  border-bottom: 1px solid #E0DFDC;
  flex-shrink: 0;
  box-shadow: 0 1px 3px rgba(44, 44, 44, 0.03);
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.project-title {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
  font-family: 'Noto Serif SC', serif;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 280px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.toolbar-btn {
  color: #5C5C5C !important;
  border-color: #E0DFDC !important;
}

.toolbar-btn:hover {
  color: #6B7B8D !important;
  border-color: #6B7B8D !important;
  background: rgba(107, 123, 141, 0.04) !important;
}

.toolbar-btn--active {
  color: #6B7B8D !important;
  border-color: #6B7B8D !important;
  background: rgba(107, 123, 141, 0.08) !important;
}

.workbench-main {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.sidebar-left {
  flex-shrink: 0;
  border-right: 1px solid #E0DFDC;
  overflow: hidden;
  background: white;
  min-width: 180px;
  max-width: 380px;
}

.editor-column {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  background: #F7F6F3;
  min-width: 0;
}

.sidebar-right {
  flex-shrink: 0;
  border-left: 1px solid #E0DFDC;
  overflow: hidden;
  background: white;
  min-width: 260px;
  max-width: 480px;
}

.resizer {
  width: 4px;
  background: transparent;
  cursor: col-resize;
  flex-shrink: 0;
  transition: background 0.15s;
}

.resizer:hover {
  background: rgba(107, 123, 141, 0.2);
}

.workbench-footer {
  display: flex;
  align-items: center;
  gap: 24px;
  height: 34px;
  padding: 0 20px;
  background: white;
  border-top: 1px solid #E0DFDC;
  flex-shrink: 0;
}

.footer-stat {
  font-size: 12px;
  color: #9E9E9E;
  display: flex;
  align-items: center;
  gap: 4px;
}

.footer-stat--current {
  color: #5C5C5C;
}

/* Add node form */
.add-node-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: #5C5C5C;
}

@media (max-width: 1024px) {
  .sidebar-right {
    width: 280px !important;
  }
}
</style>
