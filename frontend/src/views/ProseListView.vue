<template>
  <div style="padding: 24px">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">散文改写</h2>
      <div>
        <el-button type="primary" @click="$router.push('/prose/new')">+ 新建散文项目</el-button>
        <el-button @click="loadList" style="margin-left: 8px">刷新</el-button>
      </div>
    </div>

    <el-table :data="projects" v-loading="loading" style="width: 100%">
      <el-table-column label="标题" prop="title" min-width="180" />
      <el-table-column label="来源剧本" prop="script_project_title" min-width="150">
        <template #default="{ row }">
          {{ row.script_project_title || '上传文件' }}
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'generating'">
            {{ row.done_scenes + row.failed_scenes }}/{{ row.total_scenes }}
          </span>
          <span v-else>{{ row.total_scenes }} 场</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString('zh-CN') }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="$router.push(`/prose/${row.id}`)">查看</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ProseProjectOut } from '@/api/prose'
import { proseApi } from '@/api/prose'

const projects = ref<ProseProjectOut[]>([])
const loading = ref(false)

async function loadList() {
  loading.value = true
  try {
    const res = await proseApi.list()
    projects.value = res
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    pending: 'info',
    generating: 'primary',
    done: 'success',
    partial: 'warning',
    failed: 'danger',
  }
  return map[status] ?? 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '等待中',
    generating: '生成中',
    done: '完成',
    partial: '部分完成',
    failed: '失败',
  }
  return map[status] ?? status
}

async function handleDelete(row: ProseProjectOut) {
  await ElMessageBox.confirm(`确定删除「${row.title}」吗？`, '确认删除', {
    type: 'warning',
  })
  await proseApi.delete(row.id)
  ElMessage.success('已删除')
  await loadList()
}

onMounted(loadList)
</script>
