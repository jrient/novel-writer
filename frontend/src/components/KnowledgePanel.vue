<template>
  <div class="knowledge-panel">
    <div class="search-section">
      <div class="search-row">
        <el-input
          v-model="keyword"
          placeholder="输入关键词搜索并学习知识"
          @keyup.enter="handleSearch"
        >
          <template #append>
            <el-button :loading="searching" @click="handleSearch">搜索学习</el-button>
          </template>
        </el-input>
        <el-button type="primary" class="add-btn" @click="openCreateDialog">手动添加</el-button>
      </div>
      <div class="search-options">
        <el-checkbox v-model="useAI">使用AI增强搜索（更准确，稍慢）</el-checkbox>
      </div>
    </div>

    <div class="knowledge-list">
      <div v-if="loading" class="loading-state">
        <el-skeleton :rows="3" animated />
      </div>
      <el-empty v-else-if="knowledgeList.length === 0" description="暂无知识条目" />
      <el-card v-for="item in knowledgeList" :key="item.id" class="knowledge-item">
        <template #header>
          <div class="item-header">
            <span class="keyword-tag">{{ item.keyword }}</span>
            <div class="item-actions">
              <el-button text size="small" class="edit-btn" @click="openEditDialog(item)">编辑</el-button>
              <el-button text size="small" class="delete-btn" @click="handleDelete(item.id)">删除</el-button>
            </div>
          </div>
        </template>
        <h4>{{ item.title }}</h4>
        <p class="content">{{ item.content }}</p>
        <div class="meta">
          <span v-if="item.source_url" class="source">来源: {{ item.source_url }}</span>
          <span class="usage">使用次数: {{ item.usage_count }}</span>
        </div>
      </el-card>
    </div>

    <el-dialog
      :close-on-press-escape="false"
      v-model="dialogVisible"
      :title="isEditing ? '编辑知识条目' : '手动添加知识'"
      width="600px"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="关键词" required>
          <el-input v-model="form.keyword" placeholder="输入关键词" />
        </el-form-item>
        <el-form-item label="标题" required>
          <el-input v-model="form.title" placeholder="输入标题" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="form.category" placeholder="输入分类（可选）" />
        </el-form-item>
        <el-form-item label="内容" required>
          <el-input
            v-model="form.content"
            type="textarea"
            :rows="6"
            placeholder="输入知识内容"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { knowledgeApi, type KnowledgeEntry } from '@/api/knowledge'

const keyword = ref('')
const searching = ref(false)
const loading = ref(false)
const knowledgeList = ref<KnowledgeEntry[]>([])
const useAI = ref(false)

const dialogVisible = ref(false)
const isEditing = ref(false)
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = ref({ keyword: '', title: '', content: '', category: '' })

const loadKnowledge = async () => {
  loading.value = true
  try {
    knowledgeList.value = await knowledgeApi.list()
  } catch (error) {
    ElMessage.error('加载知识库失败')
  } finally {
    loading.value = false
  }
}

const handleSearch = async () => {
  if (!keyword.value.trim()) {
    ElMessage.warning('请输入关键词')
    return
  }
  searching.value = true
  try {
    const results = await knowledgeApi.search(keyword.value.trim(), 3, useAI.value)
    if (results.length === 0) {
      ElMessage.warning('未找到相关知识，请尝试其他关键词')
    } else {
      ElMessage.success(`成功学习 ${results.length} 条知识`)
      keyword.value = ''
      await loadKnowledge()
    }
  } catch (error) {
    ElMessage.error('搜索学习失败')
  } finally {
    searching.value = false
  }
}

const handleDelete = async (id: number) => {
  try {
    await knowledgeApi.delete(id)
    ElMessage.success('删除成功')
    await loadKnowledge()
  } catch (error) {
    ElMessage.error('删除失败')
  }
}

const openCreateDialog = () => {
  isEditing.value = false
  editingId.value = null
  form.value = { keyword: '', title: '', content: '', category: '' }
  dialogVisible.value = true
}

const openEditDialog = (item: KnowledgeEntry) => {
  isEditing.value = true
  editingId.value = item.id
  form.value = {
    keyword: item.keyword,
    title: item.title,
    content: item.content,
    category: item.category || '',
  }
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!form.value.keyword.trim() || !form.value.title.trim() || !form.value.content.trim()) {
    ElMessage.warning('请填写关键词、标题和内容')
    return
  }
  saving.value = true
  try {
    const data = {
      keyword: form.value.keyword.trim(),
      title: form.value.title.trim(),
      content: form.value.content.trim(),
      category: form.value.category.trim() || undefined,
    }
    if (isEditing.value && editingId.value !== null) {
      await knowledgeApi.update(editingId.value, data)
      ElMessage.success('更新成功')
    } else {
      await knowledgeApi.create(data)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await loadKnowledge()
  } catch (error) {
    ElMessage.error(isEditing.value ? '更新失败' : '创建失败')
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadKnowledge()
})
</script>

<style scoped>
.knowledge-panel {
  padding: 32px;
  height: 100%;
  overflow-y: auto;
  background: #fafaf9;
}

.search-section {
  margin-bottom: 24px;
  background: white;
  padding: 20px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.search-row {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.search-row .el-input {
  flex: 1;
}

.add-btn {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  border-radius: 8px;
  white-space: nowrap;
}

.knowledge-list {
  display: grid;
  gap: 16px;
}

.knowledge-item {
  margin-bottom: 0;
  border-radius: 12px;
  border: 1px solid #e7e5e4;
  transition: all 0.2s ease;
}

.knowledge-item:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.keyword-tag {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
}

.knowledge-item h4 {
  margin: 0 0 12px 0;
  font-size: 15px;
  font-weight: 600;
  color: #1c1917;
  line-height: 1.4;
}

.content {
  color: #57534e;
  font-size: 14px;
  line-height: 1.7;
  margin: 0 0 12px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #a8a29e;
  padding-top: 12px;
  border-top: 1px solid #f5f5f4;
}

.source {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.el-input__wrapper) {
  border-radius: 8px;
  box-shadow: none;
  border: 1px solid #e7e5e4;
}

:deep(.el-input__wrapper:hover) {
  border-color: #667eea;
}

:deep(.el-input-group__append) {
  border-radius: 0 8px 8px 0;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  color: white;
}

:deep(.el-input-group__append .el-button) {
  border: none;
  color: white;
}

.item-actions .edit-btn {
  color: #667eea !important;
}

.item-actions .delete-btn {
  color: #f56c6c !important;
}

.loading-state {
  padding: 24px;
}
</style>
