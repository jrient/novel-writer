<template>
  <div class="tree-node">
    <div class="node-content" :class="{ active: currentNodeId === node.id }" @click="$emit('select', node)">
      <span v-if="hasChildren" class="expand-btn" :class="{ expanded }" @click.stop="toggleExpand">▶</span>
      <span v-else class="expand-placeholder"></span>

      <component :is="nodeIcon" class="node-icon" :style="{ color: statusColor }" />

      <span class="node-title" :title="node.content || node.title">{{ node.title }}</span>

      <el-tag v-if="node.status !== 'planning'" :type="node.status === 'completed' ? 'success' : ''" size="small" class="node-status">
        {{ node.status === 'completed' ? '完成' : '写作中' }}
      </el-tag>
      <span v-if="node.estimated_words" class="node-words">
        {{ (node.estimated_words / 1000).toFixed(1) }}k
      </span>

      <span class="node-actions">
        <el-icon class="action-icon" @click.stop="$emit('edit', node)"><Edit /></el-icon>
        <el-icon class="action-icon danger" @click.stop="$emit('delete', node)"><Delete /></el-icon>
      </span>
    </div>

    <div v-if="hasChildren && expanded" class="node-children">
      <TreeNodeItem
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :project-id="projectId"
        :current-node-id="currentNodeId"
        @edit="$emit('edit', $event)"
        @delete="$emit('delete', $event)"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Folder, Document, List, Edit, Delete } from '@element-plus/icons-vue'
import type { OutlineNode } from '@/api/outline'

const props = defineProps<{
  node: OutlineNode
  projectId: number
  currentNodeId?: number | null
}>()

defineEmits<{
  edit: [node: OutlineNode]
  delete: [node: OutlineNode]
  select: [node: OutlineNode]
}>()

const expanded = ref(true)

const hasChildren = computed(() => props.node.children && props.node.children.length > 0)

const nodeIcon = computed(() => {
  switch (props.node.node_type) {
    case 'volume': return Folder
    case 'scene': return List
    default: return Document
  }
})

const statusColor = computed(() => {
  switch (props.node.status) {
    case 'writing': return '#667eea'
    case 'completed': return '#67c23a'
    default: return '#a8a29e'
  }
})

function toggleExpand() {
  expanded.value = !expanded.value
}
</script>

<style scoped>
.tree-node {
  user-select: none;
}

.node-content {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.node-content:hover {
  background-color: rgba(102, 126, 234, 0.06);
}

.node-content.active {
  background-color: rgba(102, 126, 234, 0.1);
}

.expand-btn {
  width: 16px;
  font-size: 10px;
  color: #a8a29e;
  transition: transform 0.2s;
  cursor: pointer;
}

.expand-btn.expanded {
  transform: rotate(90deg);
}

.expand-placeholder {
  width: 16px;
}

.node-icon {
  margin: 0 8px;
  font-size: 16px;
}

.node-title {
  flex: 1;
  font-size: 13px;
  color: #1c1917;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.node-status {
  margin-right: 4px;
  font-size: 10px;
}

.node-words {
  font-size: 11px;
  color: #a8a29e;
  margin-right: 8px;
}

.node-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.2s;
}

.node-content:hover .node-actions {
  opacity: 1;
}

.action-icon {
  font-size: 14px;
  color: #a8a29e;
  cursor: pointer;
  padding: 4px;
}

.action-icon:hover {
  color: #667eea;
}

.action-icon.danger:hover {
  color: #f56c6c;
}

.node-children {
  padding-left: 24px;
}
</style>
