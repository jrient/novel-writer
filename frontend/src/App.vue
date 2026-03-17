<template>
  <!-- 全局路由视图容器 -->
  <router-view />
</template>

<script setup lang="ts">
// 深色模式状态初始化（自动从 localStorage 恢复）
import { useTheme } from '@/composables/useTheme'

// 初始化主题系统
useTheme()
</script>

<style>
/* 全局样式已移至 src/styles/main.scss */
/* 此处仅保留组件特定覆盖 */
</style>