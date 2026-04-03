# 剧本设定侧边栏 · 设计文档

**日期**: 2026-04-03
**版本**: v1.0
**状态**: 已批准

---

## 概述

为剧本创作工作台（DramaWorkbenchView）新增一个可从右侧滑入的设定抽屉，允许用户管理人物设定、世界观、风格基调、核心剧情要素和全局 AI 指令。所有设定在每次 AI 生成时自动注入 prompt，引导 AI 保持剧本方向一致。

---

## 需求

### 功能需求

1. 工作台顶部工具栏新增「⚙ 设定」按钮，点击触发设定抽屉
2. 移除现有 GlobalDirectiveDialog 入口，逻辑合并至设定抽屉
3. 设定抽屉包含 5 个折叠面板：
   - 👤 人物设定：角色列表，每个角色有姓名 + 自由文本描述，支持增删
   - 🌍 世界观 / 背景：自由文本
   - 🎭 风格 / 基调：自由文本
   - 📌 核心剧情要素：自由文本
   - ⚡ 全局 AI 指令：自由文本（替代原 GlobalDirectiveDialog）
4. 编辑任意字段后自动防抖保存（500ms）
5. 点击角色卡片弹出 CharacterEditOverlay（出现在中央编辑区域）
6. 所有设定在每次 AI 接口调用时自动注入 system prompt（非空模块才注入）

### 非功能需求

- 无数据库 migration：数据存入已有的 `script_projects.metadata` 字段
- 设定为空时不注入 prompt，避免浪费 token

---

## 架构设计

### 数据结构

设定存入 `script_projects.metadata.settings`：

```json
{
  "settings": {
    "characters": [
      { "name": "张三", "description": "性格豪爽，说话直接，不善于表达情感..." }
    ],
    "world_setting": "架空古代，科技与魔法并存...",
    "tone": "热血励志，节奏快，对白简洁有力...",
    "plot_anchors": "主角不能死，第三集必须出现背叛情节...",
    "global_directive": "保持角色一致性，不要出现现代词汇..."
  }
}
```

### 新增组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `ScriptSettingsDrawer.vue` | `frontend/src/components/drama/` | 设定抽屉主体，5 个 el-collapse 折叠面板，防抖自动保存 |
| `CharacterEditOverlay.vue` | `frontend/src/components/drama/` | 角色编辑浮层，挂载在中央编辑区，编辑姓名 + 自由文本描述 |

### 修改组件

| 组件 | 改动 |
|------|------|
| `DramaWorkbenchView.vue` | 工具栏增加「⚙ 设定」按钮；移除 GlobalDirectiveDialog 入口；挂载 ScriptSettingsDrawer 和 CharacterEditOverlay |
| `GlobalDirectiveDialog.vue` | 删除（逻辑迁移至 ScriptSettingsDrawer） |
| `frontend/src/stores/drama.ts` | 增加 `projectSettings` 计算属性；增加 `updateProjectSettings()` action |
| `frontend/src/api/drama.ts` | 增加 `updateProjectSettings(projectId, settings)` API 函数 |

### 后端改动

| 文件 | 改动 |
|------|------|
| `backend/app/routers/drama.py` | 增加 `PUT /api/v1/drama/{id}/settings` 端点；AI 接口（expand-node、rewrite-node 等）在构建 prompt 前读取 `metadata.settings` 并注入 system prompt 头部 |

---

## 交互流程

### 打开设定抽屉

```
工具栏点击「⚙ 设定」
  → ScriptSettingsDrawer 从右侧滑入（360px，覆盖 AI 助手面板）
  → 展示 5 个 el-collapse 折叠面板
  → 编辑任意字段，防抖 500ms 后自动保存
     → PUT /api/v1/drama/{id}/settings
     → 更新 script_projects.metadata.settings
```

### 编辑角色

```
点击设定抽屉中的角色卡片（如「张三」）
  → CharacterEditOverlay 出现在中央编辑区域（浮层形式，抽屉保持可见）
  → 用户编辑姓名 + 自由文本描述
  → 点击「保存」→ 写回 settings.characters → 关闭浮层
  → 点击「取消」→ 放弃修改 → 关闭浮层
```

### AI 自动注入

每次调用 AI 接口时，后端在 system prompt 顶部自动拼入（仅注入非空模块）：

```
【剧本设定】
人物：
  - 张三：性格豪爽，说话直接...
世界观：架空古代，科技与魔法并存...
风格基调：热血励志，节奏快...
核心要素：主角不能死，第三集必须出现背叛...
全局指令：保持角色一致性，不要出现现代词汇...
```

---

## API 设计

### 新增端点

```
PUT /api/v1/drama/{project_id}/settings
```

**Request Body:**
```json
{
  "characters": [{ "name": "string", "description": "string" }],
  "world_setting": "string",
  "tone": "string",
  "plot_anchors": "string",
  "global_directive": "string"
}
```

**Response:** `200 OK`，返回更新后的 ScriptProject 对象。

**逻辑：** 将 settings 写入 `script_projects.metadata["settings"]`，其余 metadata 字段保持不变。

---

## UI 布局

```
┌─ 工作台工具栏 ──────────────────────────────────────┐
│  [项目名]                    [⚙ 设定] [AI助手] [...]  │
└────────────────────────────────────────────────────┘

┌─ 三列工作区 ─────────────────────────────────────────┐
│ 大纲树(240px) │ 编辑器(flex) │ AI助手/设定抽屉(360px) │
└────────────────────────────────────────────────────┘

设定抽屉打开时：
┌─────────────────────────────┐
│  ⚙ 剧本设定             ✕  │
├─────────────────────────────┤
│ ▼ 👤 人物设定               │
│  ┌──────────────────────┐  │
│  │ 张三            [编辑]│  │  ← 点击触发 CharacterEditOverlay
│  │ 李四            [编辑]│  │
│  └──────────────────────┘  │
│  [+ 添加角色]               │
├─────────────────────────────┤
│ ▶ 🌍 世界观 / 背景          │
├─────────────────────────────┤
│ ▶ 🎭 风格 / 基调            │
├─────────────────────────────┤
│ ▶ 📌 核心剧情要素           │
├─────────────────────────────┤
│ ▶ ⚡ 全局 AI 指令           │
└─────────────────────────────┘
```

---

## 范围说明

### 在范围内
- ScriptSettingsDrawer 和 CharacterEditOverlay 两个新组件
- DramaWorkbenchView 工具栏改动
- GlobalDirectiveDialog 删除与逻辑迁移
- Pinia store 增加 settings 状态和 action
- 后端新增 settings 端点
- 后端 AI 接口注入设定上下文

### 不在范围内
- 设定版本历史（可后续扩展）
- 设定模板库
- 人物关系图谱
- 跨项目设定共享
