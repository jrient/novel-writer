<template>
  <!-- 全局路由视图容器 -->
  <router-view />
</template>

<style>
/* 全局样式 */
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Noto Serif SC', serif;
  background-color: #1a1a2e;
  color: #e0e0e0;
  min-height: 100vh;
}

/* 滚动条样式 */
::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: #16213e;
}

::-webkit-scrollbar-thumb {
  background: #e2b714;
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: #c9a012;
}

/* Element Plus 主题覆盖 */
:root {
  --el-color-primary: #e2b714;
  --el-color-primary-dark-2: #c9a012;
  --el-color-primary-light-3: #e8c44c;
  --el-bg-color: #1a1a2e;
  --el-bg-color-overlay: #16213e;
  --el-text-color-primary: #e0e0e0;
  --el-border-color: #2d3561;
  --el-border-color-light: #2d3561;
}
</style>
