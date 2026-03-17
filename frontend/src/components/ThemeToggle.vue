<template>
  <el-tooltip :content="isDark ? '切换到浅色模式' : '切换到深色模式'" placement="bottom">
    <el-button
      :icon="isDark ? Sunny : Moon"
      circle
      @click="toggleDark()"
    />
  </el-tooltip>
</template>

<script setup lang="ts">
import { Moon, Sunny } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'

const { isDark, toggleDark } = useTheme()
</script>