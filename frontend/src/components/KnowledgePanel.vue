<template>
  <div class="knowledge-panel">
    <div class="search-section">
      <el-input
        v-model="keyword"
        placeholder="输入关键词搜索并学习知识"
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :loading="searching" @click="handleSearch">搜索学习</el-button>
        </template>
      </el-input>
      <div class="search-options">
        <el-checkbox v-model="useAI">使用AI增强搜索（更准确，稍慢）</el-checkbox>
      </div>
    </div>

    <div class="knowledge-list">
      <el-empty v-if="!loading && knowledgeList.length === 0" description="暂无知识条目" />
      <el-card v-for="item in knowledgeList" :key="item.id" class="knowledge-item">
        <template #header>
          <div class="item-header">
            <span class="keyword-tag">{{ item.keyword }}</span>
            <el-button text size="small" @click="handleDelete(item.id)">删除</el-button>
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

:deep(.el-button) {
  border: none;
  color: white;
}
</style>
