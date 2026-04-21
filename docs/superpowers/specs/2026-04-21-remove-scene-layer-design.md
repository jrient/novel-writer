# 去掉场景层 — 集作为最小内容单元

**日期：** 2026-04-21
**状态：** 已确认
**范围：** 动态漫 Wizard 流程 + AI 生成逻辑

---

## 背景与动机

当前动态漫的大纲结构为「分集 → 场景」两级。每集的内容量只有 800-1500 字，拆分为 2-4 个场景后：

- 上下场景之间内容不够连贯
- 用户需要花更多时间修改衔接问题
- 场景粒度过细，对短内容没有实际意义

**决策：去掉场景层，集是最小的内容单元。**

## 方案选择

**方案 A（已选）：最小改动 — 只改 AI 生成逻辑和 Prompt**

- 数据模型不动，`scene` node_type 保留在代码中
- AI 不再生成场景节点，改为直接生成整集纯文本内容
- 改动集中在 AI prompt 和 Wizard 流程
- 后续如需恢复场景功能，无破坏性

淘汰方案：
- 方案 B（彻底清理 scene 相关代码）— 改动面大，无明显收益
- 方案 C（配置开关兼容两种模式）— 过度设计

## 改动清单

### 1. AI Prompt 改造

**文件：** `backend/app/services/script_ai_service.py`

- `expand_episode` 方法重命名为 `generate_episode_content`
- System prompt 改为："你是一位专业的动态漫剧本撰写师，擅长将集概要展开为完整的叙事内容"
- User prompt 改为要求输出 800-1500 字纯文本剧本，对白、动作、叙事自然穿插，不分场景，不使用结构化标签
- 输出格式从 JSON 改为纯文本流
- 保留现有上下文信息（标题、摘要、前后集、故事阶段）

### 2. 后端 Router 改造

**文件：** `backend/app/routers/drama.py`

#### 2a. `session_expand_episode` 端点

- AI 返回纯文本，直接写入 `outline_draft.sections[idx].content`（覆盖原一句话概要）
- 新增标记 `outline_draft.sections[idx].generated = true`，供前端判断
- 去掉 JSON 解析/修复逻辑，改为文本拼接

#### 2b. `session_confirm_outline` 端点

- 无需改动。现有递归逻辑在 `children=[]` 时自动不递归，兼容 episode-only 结构

#### 2c. 不新增端点

- 批量生成复用现有 `session/expand-episode`，前端循环调用

### 3. 前端改造

#### 3a. `OutlineDraftPreview.vue`

- "展开场景" 按钮 → "生成内容"
- "已展开" 标签 → "已生成"
- `isExpanded` 判断逻辑：从检查 `children.length > 0` 改为检查 `generated === true`
- 删除场景列表区域（`.scene-list`）
- 生成完成后在集卡片下方显示内容预览（前 100 字 + "..."）

#### 3b. `DramaWizardView.vue`

- Step 2 副标题：`"共 N 集 · 可逐集展开或一键展开全部场景"` → `"共 N 集 · 可逐集生成或一键生成全部内容"`
- "展开全部场景" 按钮 → "生成全部内容"
- `allExpanded` 计算属性：改为检查 `generated` 标记
- 展开过程提示文案适配（"展开中" → "生成中" 等）
- 对话框文案适配（"全部重新展开" → "全部重新生成"，"跳过已展开" → "跳过已生成"）

## 不改动的部分

| 模块 | 说明 |
|------|------|
| `ScriptNode` 数据模型 | `scene` node_type 保留，不删除 |
| `ScriptNodeCreate` schema | 仍允许创建 scene 类型节点 |
| Node CRUD API | 增删改查不变 |
| `rewrite` / `expand` / `global_directive` | 保留，本次不适配 |
| 工作台编辑器组件 | 不改 |
| 解说漫流程 | 完全不受影响 |
| 导出功能 | 不改，兼容 episode-only |
| 旧数据迁移 | 不需要，无重要旧数据 |

## 技术要点

- `generate_episode_content` 不再输出 JSON，减少了 JSON 解析失败的风险
- `generated` 标记存在 `outline_draft` 的 session JSON 中，不影响数据模型
- 前端循环调用 SSE 端点进行批量生成，复用现有模式
- 改动只影响动态漫 Wizard 流程，解说漫完全隔离
