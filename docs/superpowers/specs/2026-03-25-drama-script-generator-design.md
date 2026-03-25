# 剧本生成模块设计文档

> 日期: 2026-03-25
> 状态: 已批准（v2，含 review 修正）
> 模块: Drama Script Generator

## 概述

为 novel-writer 平台新增一个**完全独立**的剧本生成功能模块，支持通过一句话故事概念，在 AI 引导下生成两种类型的剧本：

- **解说漫剧本**：以旁白叙述故事，第一/第三人称叙事，适合短视频解说、有声书
- **动态漫剧本**：以画面和对话展现故事，包含分镜描述、角色对话、特效标注，适合漫画/短剧

该模块拥有独立的入口、URL 路径、工作台、数据模型和 AI 配置，与小说模块完全分离。

## 两种剧本类型的核心区别

| 维度 | 解说漫 | 动态漫 |
|------|--------|--------|
| 叙事方式 | 旁白主导，第一/第三人称 | 对话+画面描述驱动 |
| 结构 | 导语 → 分段(1,2,3...) → 叙述段落 | 集 → 场景(地点/时间/内外景) → 对话/动作/特效 |
| 角色表现 | 对话嵌入叙述，引号标记 | 角色名标签 + 独立对话行 |
| 画面描述 | 无 | △ 标记动作，OS 标记内心独白，【】标记特效 |
| 角色外貌 | 叙述中自然描写 | 首次出场有结构化描述（性别/外貌/服装/气质） |
| 典型长度 | 数百至千行（单个完整故事） | 数千行（多集连续剧） |

## 数据模型

采用**统一节点树模型**，用一套 `ScriptProject` + `ScriptNode` 树形结构同时表达两种剧本。

### ScriptProject（剧本项目）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK → User | 所属用户 |
| title | String(200) | 剧本标题 |
| script_type | Enum('explanatory', 'dynamic') | 解说漫 / 动态漫 |
| concept | Text | 用户的一句话故事概念 |
| status | Enum('drafting', 'outlined', 'writing', 'completed') | 创作阶段 |
| ai_config | JSON | 独立 AI 配置（见下方 ai_config 结构） |
| metadata | JSON | 扩展元数据（风格、受众、预计集数等） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### ai_config JSON 结构

**安全约束**：`ai_config` **不存储 API Key 等敏感信息**。API Key 引用全局配置或通过环境变量读取。

```json
{
  "provider": "openai",
  "model": "gpt-4o",
  "temperature": 0.8,
  "max_tokens": 4096,
  "prompts": {
    "questioning": "你是一个专业的{script_type}剧本策划师...",
    "outlining": "根据以下信息生成结构化大纲...",
    "expanding": "根据大纲扩写以下场景...",
    "rewriting": "按照以下要求重写内容..."
  }
}
```

- `prompts` 中每个阶段的提示词**用户可在前端编辑**
- 系统预置解说漫/动态漫各一套默认模板，用户可修改或重置
- 支持变量插值：`{concept}`, `{history}`, `{node_context}`, `{script_type}`

### ScriptNode（剧本节点 - 树形）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| project_id | Integer FK → ScriptProject, ondelete CASCADE | 所属剧本项目 |
| parent_id | Integer FK → ScriptNode (self), ondelete CASCADE | 父节点，NULL 为根节点。**删除父节点时级联删除所有子节点** |
| node_type | Enum | 节点类型（见下方枚举） |
| title | String(200) | 节点标题（集名、场景名等） |
| content | Text | 具体文本内容 |
| speaker | String(100) | 说话人（仅 dialogue 类型，其他类型忽略） |
| visual_desc | Text | 画面描述（仅动态漫的 action/effect，其他类型忽略） |
| sort_order | Integer | 同级排序序号 |
| is_completed | Boolean, default False | 节点内容是否已完成（用户手动标记） |
| metadata | JSON | 扩展字段（角色外貌描述、特效说明等） |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**node_type 校验约束**：API 层校验 node_type 与 script_type 的匹配关系，解说漫项目不允许创建 episode/scene/dialogue/action/effect/inner_voice 类型节点，动态漫项目不允许创建 section/narration/intro 类型节点。

#### node_type 枚举值

| 类型 | 适用 | 说明 |
|------|------|------|
| `episode` | 动态漫 | 集（第1集、第2集） |
| `scene` | 动态漫 | 场景（01-1 京城大学堂 日/内） |
| `dialogue` | 动态漫 | 角色对话 |
| `action` | 动态漫 | △ 画面动作描述 |
| `effect` | 动态漫 | 【】特效/系统提示 |
| `inner_voice` | 动态漫 | OS 内心独白 |
| `section` | 解说漫 | 分段（1, 2, 3...） |
| `narration` | 解说漫 | 旁白叙述段落 |
| `intro` | 解说漫 | 导语 |

#### 层级结构示例

```
动态漫:
  episode(第1集)
    scene(01-1 京城大学堂 日/内)
      action(△宽敞的演武场内...)
      dialogue(七皇子: 哈哈哈...)
      inner_voice(OS秦天: 我是大玄皇朝...)
      effect(【你得到了大道关注】)

解说漫:
  intro(导语)
  section(1)
    narration(快递员敲门的时候...)
    narration(门刚拉开一条缝...)
  section(2)
    narration(...)
```

### ScriptSession（AI 引导会话）

每个 ScriptProject 最多有**一个活跃 Session**（`project_id` 唯一约束）。如果用户想重新走问答流程，先归档（删除）旧 session 再创建新的。

| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| project_id | Integer FK → ScriptProject, UNIQUE | 关联剧本项目（一对一） |
| state | Enum('init', 'questioning', 'outlining', 'expanding', 'completed') | 当前阶段 |
| history | JSON | 问答历史 `[{role, content}]`，最大 30 轮（超出时截断早期记录） |
| outline_draft | JSON | 大纲草稿（结构见下方） |
| current_node_id | Integer FK → ScriptNode, nullable | 当前正在扩写的节点 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### outline_draft JSON 结构

```json
{
  "nodes": [
    {
      "temp_id": "t1",
      "node_type": "episode",
      "title": "第1集",
      "summary": "秦天在演武场被嘲笑...",
      "children": [
        {
          "temp_id": "t1-1",
          "node_type": "scene",
          "title": "01-1 京城大学堂 日/内",
          "summary": "皇子们测试修行资质..."
        }
      ]
    }
  ]
}
```

## AI 引导工作流

### 状态机

```
INIT → QUESTIONING → OUTLINING → EXPANDING → COMPLETED
```

### 各阶段说明

#### 1. INIT
- 用户选择剧本类型（解说漫/动态漫）
- 输入一句话故事概念
- 系统创建 `ScriptProject` + `ScriptSession`

#### 2. QUESTIONING（动态问答）
- **不预设固定问题列表**，每次提问由 AI 基于当前上下文动态生成
- AI 输入：`剧本类型 + 用户概念 + 历史问答记录`
- AI 输出 JSON：
  - `question`: 问题文本
  - `options`: 可选参考选项（可为空，允许自由回答）
  - `should_continue`: bool，AI 判断是否还需继续追问
  - `reasoning`: 内部推理（不展示给用户）
- 用户可随时点击"跳过，直接生成大纲"提前结束
- AI 的 System Prompt 引导其关注关键维度（角色、冲突、节奏等），但具体问什么完全动态决定
- **最大提问轮数限制：30 轮**，超过后自动进入 OUTLINING

#### 3. OUTLINING
- AI 基于问答上下文生成结构化大纲（SSE 流式输出）
- 解说漫：生成 `intro` + 多个 `section` 的标题和摘要
- 动态漫：生成 `episode` 列表，每集包含 `scene` 概要
- 输出为 JSON（符合 outline_draft 结构），前端渲染为可编辑大纲树
- 用户可手动调整（拖拽、增删、改名），**每次编辑实时持久化到 outline_draft**
- 对单节点要求 AI 重新生成
- 确认后：系统将 outline_draft 转化为 ScriptNode 记录写入数据库，进入扩写阶段

#### 4. EXPANDING
- 用户选择任意大纲节点，点击"扩写"
- AI 根据节点上下文（前后节点摘要、角色信息）生成完整内容
- SSE 流式输出到编辑器
- 支持对选中文本调用 AI 重写/润色/风格转换
- 节点扩写完毕后**由用户手动点击标记为已完成**

#### 5. COMPLETED
- 所有节点扩写完毕或用户手动标记项目完成
- 可导出 TXT/Markdown

### 全局调控能力

在 EXPANDING 及之后的阶段，用户可以对剧本进行**项目级别的 AI 调整**：

| 操作 | 说明 |
|------|------|
| 全局重生成大纲 | 附带反馈重新生成整个大纲（如"节奏太慢，压缩到15集"） |
| 批量重写 | 选中多个节点 + 全局指令一起重写 |
| 全局风格调整 | 对已有内容应用风格指令（如"对话更口语化"、"增加冲突感"） |

交互方式：工作台顶部 **"全局指令"** 按钮，用户输入自然语言反馈，选择作用范围后执行。

### AI 服务层

独立的 `ScriptAIService`，不复用小说的 `AIService`：

```python
class ScriptAIService:
    """剧本专用 AI 服务"""

    async def generate_question(session) -> Question     # 动态生成下一个引导问题
    async def generate_outline(session) -> Stream        # 生成结构化大纲
    async def expand_node(node, context) -> Stream       # 扩写节点内容
    async def rewrite_content(content, instruction)      # 重写选中内容
    async def global_directive(project, instruction,     # 全局指令
                               scope, node_ids) -> Stream

    # 从 ScriptProject.ai_config 读取模型/温度配置
    # API Key 从全局配置（环境变量）读取
    # 用户自定义的 prompts 从 ai_config.prompts 读取
    # 针对解说漫/动态漫使用不同的默认 System Prompt
```

## 前端架构

### 路由

| 路径 | 视图 | 说明 |
|------|------|------|
| `/drama` | DramaListView | 剧本项目列表 |
| `/drama/create` | DramaCreateView | 创建剧本（选类型+输入概念） |
| `/drama/wizard/:id` | DramaWizardView | AI 引导问答 |
| `/drama/workbench/:id` | DramaWorkbenchView | 剧本工作台 |

**注意**：需要在 `frontend/src/router/index.ts` 中将 `/drama` 路由注册在 catch-all `/:pathMatch(.*)*` **之前**，否则会被重定向到 `/projects`。

### 页面说明

#### DramaListView — 剧本列表
- 卡片式布局，显示标题、类型标签（解说漫/动态漫）、状态、创建时间
- 支持按类型筛选
- 右上角"新建剧本"按钮
- 支持分页

#### DramaCreateView — 创建页
- 步骤一：选择剧本类型（两张卡片，配图+说明）
- 步骤二：输入故事概念（大文本框，带示例提示）
- 步骤三：配置 AI（可选展开，模型选择、温度、提示词模板编辑）
- 提交后跳转到 wizard

#### DramaWizardView — AI 引导问答
- 聊天式界面，AI 消息在左，用户回答在右
- AI 提问时下方显示选项按钮 + 自由输入框
- 顶部进度指示（问答中 → 生成大纲 → ...）
- 底部有"跳过，直接生成大纲"按钮
- 大纲生成后以可编辑树形展示，确认后跳转 workbench

#### DramaWorkbenchView — 工作台（核心）

```
┌──────────────────────────────────────────────────────┐
│  顶部栏: 返回 | 标题 | 类型标签 | 全局指令 | 导出 | AI配置 │
├──────────┬──────────────────────┬────────────────────┤
│  大纲树   │    内容编辑器         │   AI 面板         │
│          │                      │                    │
│  ▼ 第1集  │  [富文本/结构化编辑]  │  扩写本节点        │
│   ☑场景1  │                      │  重写选中文本      │
│    场景2  │                      │  风格转换          │
│  ▼ 第2集  │                      │  添加对话          │
│    ...   │                      │  添加动作描述      │
│          │                      │                    │
│  [+新节点]│                      │                    │
├──────────┴──────────────────────┴────────────────────┤
│  状态栏: 节点数 | 已完成/总数 | 字数统计              │
└──────────────────────────────────────────────────────┘
```

- **左侧大纲树**：拖拽排序，右键菜单（重命名/删除/插入/AI重新生成），节点图标区分类型，☑ 标记已完成节点
- **中间编辑器**：基于 Tiptap，内容以 HTML 存储到 `ScriptNode.content`
  - 解说漫：纯叙事文本，段落分明
  - 动态漫：角色名加粗居中，△ 动作灰色斜体，【】特效高亮，OS 旁白特殊样式
  - 使用 Tiptap Extension 实现动态漫的块类型切换
- **右侧 AI 面板**：根据当前节点动态变化操作项，可收起
- **顶部全局指令**：弹出对话框，输入指令 + 选择范围（大纲/全部节点/选中节点）

### 前端文件组织

```
frontend/src/
├── views/
│   ├── DramaListView.vue
│   ├── DramaCreateView.vue
│   ├── DramaWizardView.vue
│   └── DramaWorkbenchView.vue
├── api/
│   └── drama.ts              # API 调用 + TypeScript 类型定义
├── stores/
│   └── drama.ts
└── components/
    └── drama/
        ├── ScriptOutlineTree.vue
        ├── ScriptEditor.vue
        ├── ScriptAiPanel.vue
        ├── GlobalDirectiveDialog.vue
        ├── AiConfigPanel.vue
        ├── WizardChat.vue
        └── NodeTypeIcon.vue
```

## 后端 API

### 路由前缀

`/api/v1/drama/` — 独立于小说的 `/api/v1/projects/`

**权限校验**：所有 API 需验证 `project.user_id == current_user.id`，使用类似现有 `get_project_with_auth` 的依赖注入。

### 剧本项目 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/drama/` | 创建剧本项目 |
| GET | `/drama/` | 获取用户剧本列表（支持分页、按 script_type 筛选） |
| GET | `/drama/{id}` | 获取剧本详情 |
| PUT | `/drama/{id}` | 更新剧本信息 |
| DELETE | `/drama/{id}` | 删除剧本（级联删除所有节点和 session） |
| PUT | `/drama/{id}/ai-config` | 更新 AI 配置（含提示词模板） |

### AI 引导会话

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/drama/{id}/session` | 获取或创建引导会话（幂等，已存在则返回现有的） |
| DELETE | `/drama/{id}/session` | 删除当前会话（用于重新开始问答流程） |
| POST | `/drama/{id}/session/answer` | 提交回答，返回 AI 下一个问题（SSE） |
| POST | `/drama/{id}/session/skip` | 跳过问答，进入大纲生成 |
| POST | `/drama/{id}/session/generate-outline` | 生成大纲（SSE 流式） |
| POST | `/drama/{id}/session/confirm-outline` | 确认大纲，将 outline_draft 写入 ScriptNode |

### 剧本节点 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/drama/{id}/nodes` | 获取所有节点（树形结构） |
| POST | `/drama/{id}/nodes` | 创建节点（校验 node_type 与 script_type 匹配） |
| PUT | `/drama/{id}/nodes/{node_id}` | 更新节点内容/标题/完成状态 |
| DELETE | `/drama/{id}/nodes/{node_id}` | 删除节点（级联删除子节点） |
| PUT | `/drama/{id}/nodes/reorder` | 批量重排序 |

### AI 内容生成

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/drama/{id}/nodes/{node_id}/expand` | 扩写节点（SSE） |
| POST | `/drama/{id}/ai/rewrite` | 重写选中内容（SSE） |
| POST | `/drama/{id}/ai/global-directive` | 全局指令（SSE） |

`global-directive` 请求体：
```json
{
  "instruction": "节奏太慢，每集冲突更密集，总集数压缩到15集",
  "scope": "outline | all_nodes | selected_nodes",
  "node_ids": [1, 2, 3]
}
```

### 导出

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/drama/{id}/export?format=txt` | 导出 TXT |
| GET | `/drama/{id}/export?format=markdown` | 导出 Markdown |

### 后端文件组织

```
backend/app/
├── models/
│   ├── script_project.py      # ScriptProject 模型
│   ├── script_node.py         # ScriptNode 模型
│   └── script_session.py      # ScriptSession 模型
├── schemas/
│   └── drama.py               # 所有 Pydantic schema（含请求/响应类型）
├── routers/
│   └── drama.py               # 路由层
├── services/
│   └── script_ai_service.py   # 剧本专用 AI 服务
└── scripts/
    └── migrate_add_drama.py   # 数据库迁移脚本
```

## 实现注意事项

### 数据库迁移
- 新增 3 张表：`script_projects`、`script_nodes`、`script_sessions`
- 需编写迁移脚本 `backend/scripts/migrate_add_drama.py`（与现有迁移脚本风格一致）
- 新模型需在 `backend/app/models/__init__.py` 的 `__all__` 中注册

### SSE 中间件兼容
- 现有 `backend/app/middleware/request_logging.py` 中 `SSE_PATH_KEYWORDS` 仅包含 `/ai/generate` 等路径
- 需添加 `/drama/` 相关 SSE 路径，或改为更通用的 SSE 检测机制

### 路由注册
- 后端：在 `backend/app/main.py` 中注册新的 drama router
- 前端：在 `frontend/src/router/index.ts` 中注册 `/drama` 路由（在 catch-all 之前）

### 错误处理
- AI 生成失败（超时、token 超限、provider 不可用）时返回明确错误信息
- 前端显示错误提示并允许重试
- ScriptAIService 在未配置 AI 时返回友好提示
