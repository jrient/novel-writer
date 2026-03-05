<template>
  <div class="ai-panel">
    <!-- 面板标题 -->
    <div class="panel-header">
      <el-icon class="ai-icon"><MagicStick /></el-icon>
      <h3>AI 助手</h3>
    </div>

    <!-- 当前章节信息 -->
    <div class="chapter-info" v-if="currentChapterTitle">
      <p class="info-label">当前章节</p>
      <p class="chapter-name">{{ currentChapterTitle }}</p>
    </div>

    <!-- AI 功能按钮组 -->
    <div class="ai-actions">
      <p class="section-title">创作辅助</p>

      <el-tooltip content="AI 将根据当前内容续写故事" placement="left">
        <el-button class="ai-btn" disabled>
          <el-icon><Promotion /></el-icon>
          续写故事
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将改写选中的段落" placement="left">
        <el-button class="ai-btn" disabled>
          <el-icon><Edit /></el-icon>
          改写润色
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将扩写当前内容" placement="left">
        <el-button class="ai-btn" disabled>
          <el-icon><Plus /></el-icon>
          扩写内容
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将为故事生成大纲" placement="left">
        <el-button class="ai-btn" disabled>
          <el-icon><Document /></el-icon>
          生成大纲
        </el-button>
      </el-tooltip>

      <el-tooltip content="AI 将分析角色性格与发展" placement="left">
        <el-button class="ai-btn" disabled>
          <el-icon><User /></el-icon>
          角色分析
        </el-button>
      </el-tooltip>
    </div>

    <!-- 占位提示 -->
    <div class="coming-soon">
      <el-icon><InfoFilled /></el-icon>
      <p>AI 功能将在后续版本中开放</p>
      <p class="sub-text">敬请期待</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { MagicStick, Promotion, Edit, Plus, Document, User, InfoFilled } from '@element-plus/icons-vue'

// 接收当前章节标题
defineProps<{
  currentChapterTitle?: string
}>()
</script>

<style scoped>
.ai-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  background-color: #16213e;
  overflow-y: auto;
}

/* 面板标题 */
.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 16px;
  border-bottom: 1px solid #2d3561;
  margin-bottom: 16px;
}

.ai-icon {
  font-size: 20px;
  color: #e2b714;
}

.panel-header h3 {
  font-size: 16px;
  font-weight: 600;
  color: #e0e0e0;
  margin: 0;
}

/* 章节信息 */
.chapter-info {
  background: rgba(226, 183, 20, 0.05);
  border: 1px solid rgba(226, 183, 20, 0.2);
  border-radius: 6px;
  padding: 10px 12px;
  margin-bottom: 16px;
}

.info-label {
  font-size: 11px;
  color: #909399;
  margin-bottom: 4px;
}

.chapter-name {
  font-size: 13px;
  color: #e2b714;
  font-weight: 500;
}

/* 功能按钮区 */
.ai-actions {
  flex: 1;
}

.section-title {
  font-size: 12px;
  color: #606266;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ai-btn {
  width: 100%;
  margin-bottom: 8px;
  background-color: #1a1a2e;
  border-color: #2d3561;
  color: #909399;
  justify-content: flex-start;
  gap: 8px;
  height: 40px;
  cursor: not-allowed;
}

.ai-btn:hover {
  border-color: #2d3561;
  background-color: #1a1a2e;
  color: #909399;
}

/* 开放提示 */
.coming-soon {
  text-align: center;
  padding: 20px 0;
  border-top: 1px solid #2d3561;
  margin-top: 16px;
  color: #606266;
}

.coming-soon .el-icon {
  font-size: 24px;
  margin-bottom: 8px;
  color: #e2b714;
  opacity: 0.5;
}

.coming-soon p {
  font-size: 13px;
  margin-bottom: 4px;
}

.sub-text {
  font-size: 11px;
  color: #4a4a5a;
}
</style>
