<template>
  <div class="expansion-workbench-page">
    <header class="page-header">
      <div class="header-content">
        <div class="header-left">
          <el-button text :icon="ArrowLeft" @click="router.push('/expansion')">返回列表</el-button>
          <h1 class="page-title">扩写工作台</h1>
        </div>
      </div>
    </header>
    <main class="page-main">
      <el-card class="workbench-card">
        <div class="placeholder-content">
          <el-empty description="工作台页面 - Task 12 待实现" />
        </div>
      </el-card>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'

const router = useRouter()
</script>

<style scoped>
.expansion-workbench-page {
  min-height: 100vh;
  background-color: #F0EFEC;
}

.page-header {
  background-color: white;
  border-bottom: 1px solid #E0DFDC;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
}

.header-content {
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #2C2C2C;
  margin: 0;
}

.page-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 32px;
}

.workbench-card {
  border-radius: 14px;
}

.placeholder-content {
  min-height: 500px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>