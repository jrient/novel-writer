<template>
  <div class="outline-tree">
    <div class="tree-header">
      <span class="tree-title">大纲结构</span>
    </div>

    <div class="tree-body">
      <el-empty v-if="!nodes.length" description="暂无节点" :image-size="60" />

      <el-tree
        v-else
        :data="treeData"
        :props="{ label: 'title', children: 'children' }"
        node-key="id"
        :current-node-key="currentNodeId ?? undefined"
        highlight-current
        default-expand-all
        @node-click="handleNodeClick"
        class="script-tree"
      >
        <template #default="{ data }">
          <div
            class="tree-node"
            @contextmenu.prevent="showContextMenu($event, data)"
          >
            <NodeTypeIcon :node-type="data.node_type" size="small" />
            <span class="node-label" :class="{ 'node-label--completed': data.is_completed }">
              {{ getNodeLabel(data) }}
            </span>
            <el-icon v-if="data.is_completed" class="check-icon"><Select /></el-icon>
          </div>
        </template>
      </el-tree>
    </div>

    <div class="tree-footer">
      <el-button
        text
        size="small"
        :icon="Plus"
        class="add-node-btn"
        @click="emit('add-node', null)"
      >
        新节点
      </el-button>
    </div>

    <!-- Context menu -->
    <div
      v-if="contextMenu.visible"
      class="context-menu"
      :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }"
      @mouseleave="contextMenu.visible = false"
    >
      <div class="context-menu-item" @click="handleRename">
        <el-icon><Edit /></el-icon> 重命名
      </div>
      <div class="context-menu-item" @click="handleAddChild">
        <el-icon><Plus /></el-icon> 添加子节点
      </div>
      <div class="context-menu-item context-menu-item--danger" @click="handleDelete">
        <el-icon><Delete /></el-icon> 删除
      </div>
    </div>
    <div v-if="contextMenu.visible" class="context-menu-mask" @click="contextMenu.visible = false" />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, onMounted, onUnmounted } from 'vue'
import { Plus, Edit, Delete, Select } from '@element-plus/icons-vue'
import type { ScriptNode } from '@/api/drama'
import NodeTypeIcon from './NodeTypeIcon.vue'

const props = defineProps<{
  nodes: ScriptNode[]
  scriptType: 'explanatory' | 'dynamic'
  currentNodeId: number | null
}>()

const emit = defineEmits<{
  (e: 'select-node', node: ScriptNode): void
  (e: 'add-node', parentId: number | null): void
  (e: 'delete-node', nodeId: number): void
  (e: 'rename-node', nodeId: number): void
}>()

const contextMenu = reactive({
  visible: false,
  x: 0,
  y: 0,
  node: null as ScriptNode | null,
})

// API already returns nested tree structure, use directly
const treeData = computed(() => props.nodes)

function getNodeLabel(data: ScriptNode): string {
  if (data.title) return data.title
  if (data.node_type === 'dialogue' && data.speaker) {
    const preview = data.content ? data.content.slice(0, 20) : ''
    return `${data.speaker}：${preview}${data.content && data.content.length > 20 ? '...' : ''}`
  }
  if (data.content) {
    return data.content.slice(0, 30) + (data.content.length > 30 ? '...' : '')
  }
  return '未命名'
}

function handleNodeClick(data: ScriptNode) {
  emit('select-node', data)
}

function showContextMenu(e: MouseEvent, node: ScriptNode) {
  contextMenu.visible = true
  contextMenu.x = e.clientX
  contextMenu.y = e.clientY
  contextMenu.node = node
}

function handleRename() {
  if (contextMenu.node) emit('rename-node', contextMenu.node.id)
  contextMenu.visible = false
}

function handleAddChild() {
  if (contextMenu.node) emit('add-node', contextMenu.node.id)
  contextMenu.visible = false
}

function handleDelete() {
  if (contextMenu.node) emit('delete-node', contextMenu.node.id)
  contextMenu.visible = false
}

function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') contextMenu.visible = false
}

onMounted(() => document.addEventListener('keydown', handleKeyDown))
onUnmounted(() => document.removeEventListener('keydown', handleKeyDown))
</script>

<style scoped>
.outline-tree {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: white;
  overflow: hidden;
}

.tree-header {
  padding: 16px 16px 10px;
  border-bottom: 1px solid #ECEAE6;
  flex-shrink: 0;
}

.tree-title {
  font-size: 13px;
  font-weight: 600;
  color: #5C5C5C;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.tree-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.tree-footer {
  padding: 8px 12px;
  border-top: 1px solid #ECEAE6;
  flex-shrink: 0;
}

.add-node-btn {
  color: #6B7B8D !important;
  width: 100%;
  justify-content: flex-start;
}

.add-node-btn:hover {
  background: rgba(107, 123, 141, 0.06) !important;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding-right: 8px;
  overflow: hidden;
}

.node-label {
  flex: 1;
  font-size: 13px;
  color: #2C2C2C;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-label--completed {
  color: #9E9E9E;
  text-decoration: line-through;
}

.check-icon {
  color: #67c23a;
  font-size: 12px;
  flex-shrink: 0;
}

/* Context menu */
.context-menu {
  position: fixed;
  z-index: 3000;
  background: white;
  border: 1px solid #E0DFDC;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(44, 44, 44, 0.12);
  padding: 4px 0;
  min-width: 140px;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: 13px;
  color: #2C2C2C;
  cursor: pointer;
  transition: background 0.15s;
}

.context-menu-item:hover {
  background: #F7F6F3;
}

.context-menu-item--danger {
  color: #f56c6c;
}

.context-menu-item--danger:hover {
  background: #fff5f5;
}

.context-menu-mask {
  position: fixed;
  inset: 0;
  z-index: 2999;
}

/* Element Plus tree overrides */
:deep(.el-tree-node__content) {
  height: 34px;
  border-radius: 6px;
  margin: 1px 8px;
  padding-left: 8px !important;
}

:deep(.el-tree-node__content:hover) {
  background: rgba(107, 123, 141, 0.06) !important;
}

:deep(.el-tree-node.is-current > .el-tree-node__content) {
  background: rgba(107, 123, 141, 0.10) !important;
}

:deep(.el-tree-node__expand-icon) {
  color: #9E9E9E;
}
</style>
