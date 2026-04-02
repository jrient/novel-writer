# 剧本节点版本历史

## 概述

为剧本编辑器的 episode（集）节点添加版本历史功能。每次 AI 应用、切换节点、手动保存时自动/手动创建内容快照，支持查看和恢复历史版本。

## 数据层

新建 `script_node_versions` 表：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | int PK | 主键 |
| node_id | int FK → script_nodes | 关联节点 |
| version_number | int | 递增版本号（每节点独立递增） |
| title | str(200) | 标题快照 |
| content | text | 内容快照 |
| source | str(20) | 来源：`init` / `ai_apply` / `switch` / `manual` |
| created_at | datetime | 创建时间 |

约束：
- 每个节点最多保留 20 个版本，超出时删除最旧的
- 仅对 `episode` 类型节点生效
- version_number 在同一 node_id 内递增

## 后端 API

### 查询版本列表
- `GET /drama/{id}/nodes/{node_id}/versions`
- 返回：版本列表，按 version_number 倒序
- 响应字段：id, version_number, title, source, created_at

### 创建版本快照
- `POST /drama/{id}/nodes/{node_id}/versions`
- 请求体：`{ "source": "ai_apply" | "switch" | "manual" }`
- 逻辑：读取当前节点内容，创建快照，超过 20 个时删除最旧版本
- 仅允许 episode 类型节点

### 恢复版本
- `POST /drama/{id}/nodes/{node_id}/versions/{version_id}/restore`
- 逻辑：将版本的 title/content 写回节点，同时为恢复前的内容创建一个新版本（source=manual）

## 自动快照触发点

1. **初始化（source=init）**：大纲确认写入 script_nodes 时（`confirm_outline` 端点），为每个 episode 创建 version_number=1 的初始版本
2. **AI 应用（source=ai_apply）**：前端点击"应用"时，先 POST 创建快照，再 PUT 更新节点内容
3. **切换节点（source=switch）**：前端切换 episode 时，如果内容相比上次加载有变更，POST 创建快照

## 前端交互

### 历史版本按钮
- 位置：ScriptEditor 组件 header 区域
- 仅 episode 节点显示
- 按钮文案："历史版本"

### 版本列表对话框
- 使用 el-dialog 或 el-drawer
- 展示：版本号、来源标签（init/ai_apply/switch/manual 用不同颜色 el-tag）、创建时间
- 点击版本可预览内容（展开/折叠）
- "恢复此版本"按钮，二次确认后恢复

### AI 应用流程变更
- 原流程：点击"应用" → handleSaveNode({ content })
- 新流程：点击"应用" → POST 创建快照(source=ai_apply) → handleSaveNode({ content })

### 切换节点流程变更
- 在 handleSelectNode 中，如果当前节点是 episode 且内容有变更，先 POST 创建快照(source=switch)

## 不做的事

- 不对 scene、dialogue 等非 episode 节点记录版本
- 不在每次防抖自动保存时创建版本（太频繁）
- 不做版本 diff 对比（MVP 阶段只做查看和恢复）
