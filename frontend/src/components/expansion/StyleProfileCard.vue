<template>
  <el-card class="style-profile-card" shadow="never">
    <template #header>
      <div class="card-header">
        <span class="header-title">文风画像</span>
        <el-tag v-if="!profile" type="info" size="small">待分析</el-tag>
      </div>
    </template>

    <div v-if="loading" class="loading-area">
      <el-skeleton :rows="4" animated />
    </div>

    <div v-else-if="!profile" class="empty-area">
      <el-empty description="暂无文风分析数据" :image-size="60" />
    </div>

    <el-descriptions v-else :column="1" border size="small">
      <el-descriptions-item label="叙事视角">
        {{ profile.narrative_pov || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="语气基调">
        {{ profile.tone || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="句式特征">
        {{ profile.sentence_style || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="用词偏好">
        {{ profile.vocabulary || '-' }}
      </el-descriptions-item>
      <el-descriptions-item label="节奏感">
        {{ profile.rhythm || '-' }}
      </el-descriptions-item>
      <el-descriptions-item v-if="profile.notable_features" label="显著特点">
        {{ profile.notable_features }}
      </el-descriptions-item>
    </el-descriptions>
  </el-card>
</template>

<script setup lang="ts">
defineProps<{
  profile: Record<string, unknown> | null
  loading?: boolean
}>()
</script>

<style scoped>
.style-profile-card {
  border: 1px solid #E0DFDC;
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: #2C2C2C;
}

.loading-area,
.empty-area {
  padding: 20px 0;
}

:deep(.el-descriptions__label) {
  width: 80px;
  font-weight: 500;
}

:deep(.el-descriptions__content) {
  color: #5C5C5C;
}
</style>