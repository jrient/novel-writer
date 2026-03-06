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
    const results = await knowledgeApi.search(keyword.value.trim())
    ElMessage.success(`成功学习 ${results.length} 条知识`)
    keyword.value = ''
    await loadKnowledge()
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
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.search-section {
  margin-bottom: 20px;
}

.knowledge-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.knowledge-item {
  margin-bottom: 0;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.keyword-tag {
  background: #e2b714;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.knowledge-item h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.content {
  color: #666;
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 8px 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: #999;
}

.source {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
