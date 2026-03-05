<template>
  <div class="outline-panel">
    <!-- 面板头部 -->
    <div class="panel-header">
      <span class="panel-title">故事大纲</span>
      <el-dropdown @command="handleAddNode">
        <el-button size="small" type="primary" :icon="Plus">
          添加节点
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="volume">添加卷</el-dropdown-item>
            <el-dropdown-item command="chapter">添加章节</el-dropdown-item>
            <el-dropdown-item command="scene">添加场景</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 大纲树 -->
    <div class="outline-tree">
      <div v-if="outlineStore.loading" class="loading-state">
        <el-skeleton :rows="3" animated />
      </div>

      <div v-else-if="treeData.length === 0" class="empty-state">
        <el-empty description="暂无大纲" :image-size="60">
          <el-button size="small" type="primary" @click="handleAddNode('chapter')">
            创建第一个节点
          </el-button>
        </el-empty>
      </div>

      <div v-else class="tree-container">
        <TreeNodeItem
          v-for="node in treeData"
          :key="node.id"
          :node="node"
          :project-id="projectId"
          :current-node-id="currentNode?.id"
          @edit="editNode"
          @delete="confirmDelete"
          @select="selectNode"
        />
      </div>
    </div>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="showEditDialog"
      :title="editingNode ? '编辑节点' : '新建节点'"
      width="600px"
      :close-on-click-modal="false"
    >
      <el-form :model="formData" label-width="80px" label-position="left">
        <el-form-item label="标题" required>
          <el-input v-model="formData.title" placeholder="节点标题" />
        </el-form-item>

        <el-form-item label="类型">
          <el-select v-model="formData.node_type" style="width: 100%">
            <el-option label="卷" value="volume" />
            <el-option label="章节" value="chapter" />
            <el-option label="场景" value="scene" />
          </el-select>
        </el-form-item>

        <el-form-item label="内容">
          <el-input v-model="formData.content" type="textarea" :rows="4" placeholder="大纲内容/情节要点..." />
        </el-form-item>

        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="状态">
              <el-select v-model="formData.status" style="width: 100%">
                <el-option label="规划中" value="planning" />
                <el-option label="写作中" value="writing" />
                <el-option label="已完成" value="completed" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预估字数">
              <el-input-number v-model="formData.estimated_words" :min="0" :step="1000" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="备注">
          <el-input v-model="formData.notes" type="textarea" :rows="2" placeholder="备注信息..." />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveNode">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { useOutlineStore } from '@/stores/outline'
import type { OutlineNode } from '@/api/outline'
import TreeNodeItem from './TreeNodeItem.vue'

const props = defineProps<{
  projectId: number
}>()

const outlineStore = useOutlineStore()

const treeData = computed(() => outlineStore.treeData)
const currentNode = computed(() => outlineStore.currentNode)

const showEditDialog = ref(false)
const editingNode = ref<OutlineNode | null>(null)
const saving = ref(false)

const formData = ref({
  title: '',
  node_type: 'chapter',
  content: '',
  status: 'planning',
  estimated_words: undefined as number | undefined,
  notes: '',
  parent_id: undefined as number | undefined,
  level: undefined as number | undefined,
})

function handleAddNode(type: string) {
  editingNode.value = null
  formData.value = {
    title: '',
    node_type: type,
    content: '',
    status: 'planning',
    estimated_words: type === 'scene' ? 500 : type === 'chapter' ? 3000 : undefined,
    notes: '',
    parent_id: undefined,
    level: type === 'volume' ? 1 : type === 'chapter' ? 2 : 3,
  }
  showEditDialog.value = true
}

function selectNode(node: OutlineNode) {
  outlineStore.setCurrentNode(node)
}

function editNode(node: OutlineNode) {
  editingNode.value = node
  formData.value = {
    title: node.title,
    node_type: node.node_type,
    content: node.content || '',
    status: node.status,
    estimated_words: node.estimated_words ?? undefined,
    notes: node.notes || '',
    parent_id: node.parent_id ?? undefined,
    level: node.level,
  }
  showEditDialog.value = true
}

async function saveNode() {
  if (!formData.value.title) return
  saving.value = true
  try {
    if (editingNode.value) {
      await outlineStore.updateNode(props.projectId, editingNode.value.id, formData.value)
    } else {
      await outlineStore.createNode(props.projectId, formData.value)
    }
    showEditDialog.value = false
    await outlineStore.fetchTree(props.projectId)
  } finally {
    saving.value = false
  }
}

async function confirmDelete(node: OutlineNode) {
  await ElMessageBox.confirm(`确定要删除「${node.title}」吗？`, '删除确认', { type: 'warning' })
  await outlineStore.removeNode(props.projectId, node.id)
  await outlineStore.fetchTree(props.projectId)
}

onMounted(() => {
  outlineStore.fetchTree(props.projectId)
})
</script>

<style scoped>
.outline-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #16213e;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #2d3561;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: #e2b714;
}

.outline-tree {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.tree-container {
  padding: 8px 0;
}

.loading-state,
.empty-state {
  padding: 24px;
}

:deep(.el-dialog) {
  background-color: #16213e;
  border: 1px solid #2d3561;
}

:deep(.el-dialog__title) {
  color: #e0e0e0;
}

:deep(.el-form-item__label) {
  color: #c0c4cc;
}

:deep(.el-input__wrapper) {
  background-color: #1a1a2e;
  border-color: #2d3561;
}

:deep(.el-input__inner) {
  color: #e0e0e0;
}

:deep(.el-textarea__inner) {
  background-color: #1a1a2e;
  color: #e0e0e0;
  border-color: #2d3561;
}
</style>