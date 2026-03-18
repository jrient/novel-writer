# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-03-18

### Added
- AI 自动生成章节标题 - 根据章节内容智能生成标题（章节列表悬停显示魔法棒按钮）
- 角色分析功能移至角色管理面板 - 选中角色后可直接进行 AI 分析，结果内联展示
- 大纲生成功能移至大纲面板 - 在大纲页面头部直接生成，支持追加到已有内容

### Changed
- AI 助手面板精简 - 移除角色分析和生成大纲按钮，使其更聚焦于写作辅助

## [1.2.0] - 2026-03-13

### Added
- AI 除痕功能 - 清理 AI 生成内容的痕迹
- 创作向导模块 V1.1 改进
  - 新增步骤：作品设定、人物设定、确认生成
  - 优化向导流程体验
- 章节版本管理功能
- 事件管理模块
- 笔记管理模块
- AI Provider 抽象层，支持多模型路由

### Fixed
- 修复向导模块多个 bug
- 修复批量写作因连接超时导致中断的问题
- 加强批量生成章节字数约束

## [1.1.0] - 2026-03-09

### Added
- 小说创作向导模块
  - 智能生成小说大纲
  - 分卷分章规划
  - 角色和世界观引导
- 章节批量删除功能
- AI 生成时补充角色背景和外貌信息

### Fixed
- 修复导入脚本缺少去重逻辑
- 修复批量生成章节间衔接不连贯问题
- 修复 Ollama 流式输出不是真正流式的问题

## [1.0.0] - 2026-03-06

### Added
- 项目管理 CRUD
- 章节编辑器 (Tiptap 富文本)
- 自动保存与字数统计
- 三栏工作台布局
- Story Bible 系统
  - 角色管理 CRUD
  - 世界观设定管理
  - 大纲树系统
- AI 核心能力
  - 多模型支持 (OpenAI / Claude / Ollama / Gemini)
  - SSE 流式响应
  - 智能续写
  - 批量章节生成
- 参考资料/文风分析系统
  - 小说导入与向量化
  - 语义搜索
- 导出功能 (TXT/Markdown)
- Docker Compose 一键部署
- 请求 ID 追踪
- CORS 白名单配置
- 全局异常处理

### Security
- 环境变量敏感信息隔离
- CORS 白名单配置

---

## 版本说明

- **主版本号 (Major)**: 不兼容的 API 变更
- **次版本号 (Minor)**: 向后兼容的功能新增
- **修订号 (Patch)**: 向后兼容的问题修复