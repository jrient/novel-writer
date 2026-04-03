# 剧本设定侧边栏 · 设计文档

**日期**: 2026-04-03
**版本**: v1.1
**状态**: 评审中

---

## 概述

为剧本创作工作台（DramaWorkbenchView）新增一个可从右侧滑入的设定抽屉，允许用户管理人物设定、世界观、风格基调、核心剧情要素和持久化 AI 指令。所有设定在每次 AI 生成时自动注入 system prompt，引导 AI 保持剧本方向一致。

> **注意**：现有的 GlobalDirectiveDialog 是「执行型」工具（选范围 + 实时 SSE 执行），与本功能的「持久化注入」定位不同，**予以保留**，不做删除。

---

## 需求

### 功能需求

1. 工作台顶部工具栏新增「⚙ 设定」按钮，点击触发设定抽屉（原 GlobalDirectiveDialog 按钮保留）
2. 设定抽屉包含 5 个折叠面板（`el-collapse`）：
   - 👤 人物设定：角色列表，每个角色有 id + 姓名 + 自由文本描述，支持增删
   - 🌍 世界观 / 背景：自由文本（最多 3000 字符）
   - 🎭 风格 / 基调：自由文本（最多 1000 字符）
   - 📌 核心剧情要素：自由文本（最多 3000 字符）
   - ⚡ 持久化 AI 指令：自由文本（最多 2000 字符），每次 AI 调用自动注入，区别于 GlobalDirectiveDialog 的按需执行
3. 编辑任意字段后，全局共用一个 500ms 防抖定时器，到期发送完整 settings 对象保存
4. 点击角色卡片弹出 CharacterEditOverlay（浮层出现在中央编辑区域，抽屉保持可见）
5. 所有设定在每次 AI 接口调用时自动注入 system prompt 头部（空模块不注入）
6. 抽屉使用 `el-drawer`，`direction="rtl"`，`:modal="false"`，无遮罩，覆盖 AI 助手面板但不影响其他布局列

### 非功能需求

- 无数据库 migration：数据存入已有的 `script_projects.metadata_` 字段（`metadata_["settings"]` 子键）
- 设定为空时不注入 prompt，避免浪费 token
- 旧项目 `metadata_` 中无 `settings` 键时，前端和后端均以空默认值处理（不报错）

---

## 架构设计

### 数据结构

设定存入后端 `project.metadata_["settings"]`，前端对应 `project.metadata_!["settings"]`：

> **字段名说明**：后端 SQLAlchemy 模型属性为 `metadata_`（下划线，避开保留字），数据库列名为 `metadata`，Pydantic schema 序列化后 JSON key 为 `metadata_`，前端 TypeScript 类型同为 `metadata_`。

```json
{
  "settings": {
    "characters": [
      { "id": "char_uuid_1", "name": "张三", "description": "性格豪爽，说话直接..." }
    ],
    // id 由前端使用 crypto.randomUUID() 生成
    "world_setting": "架空古代，科技与魔法并存...",
    "tone": "热血励志，节奏快，对白简洁有力...",
    "plot_anchors": "主角不能死，第三集必须出现背叛情节...",
    "persistent_directive": "保持角色一致性，不要出现现代词汇..."
  }
}
```

**字段限制**：
- `characters`：最多 50 个角色，每个 `name` ≤ 100 字符，`description` ≤ 2000 字符
- `world_setting`、`plot_anchors`：≤ 3000 字符
- `tone`：≤ 1000 字符
- `persistent_directive`：≤ 2000 字符

**默认值 fallback**（旧项目兼容）：
```typescript
const defaultSettings: ProjectSettings = {
  characters: [],
  world_setting: '',
  tone: '',
  plot_anchors: '',
  persistent_directive: ''
}
// store 中: project.metadata_?.settings ?? defaultSettings
```

### 新增组件

| 组件 | 路径 | 职责 |
|------|------|------|
| `ScriptSettingsDrawer.vue` | `frontend/src/components/drama/` | 设定抽屉主体，5 个 el-collapse 折叠面板，防抖自动保存，显示保存状态 |
| `CharacterEditOverlay.vue` | `frontend/src/components/drama/` | 角色编辑浮层，挂载在中央编辑区，编辑姓名 + 自由文本描述，支持 Esc 关闭、Ctrl+Enter 保存 |

### 修改组件

| 组件 | 改动 |
|------|------|
| `DramaWorkbenchView.vue` | 工具栏增加「⚙ 设定」按钮；保留 GlobalDirectiveDialog 按钮不变；挂载 ScriptSettingsDrawer 和 CharacterEditOverlay |
| `frontend/src/stores/drama.ts` | 增加 `projectSettings` 计算属性（含 defaultSettings fallback）；增加 `updateProjectSettings(settings)` action |
| `frontend/src/api/drama.ts` | 增加 `updateProjectSettings(projectId, settings)` 函数 |

**GlobalDirectiveDialog.vue 不做任何改动。**

### 后端改动

| 文件 | 改动 |
|------|------|
| `backend/app/routers/drama.py` | 新增 `PUT /api/v1/drama/{id}/settings` 端点；修改 `ScriptAIService` 实例化调用，传入 `project_settings` |
| `backend/app/services/script_ai_service.py`（或同等路径） | `ScriptAIService.__init__` 增加 `project_settings: dict \| None = None` 参数；`_build_messages` 或 `_get_system_prompt` 中将非空设定拼入 system prompt 头部 |

---

## AI 注入机制（详细）

### 受影响的 AI 端点（全部）

| 端点 | 是否注入 |
|------|---------|
| `POST /nodes/{id}/expand` | ✅ 注入 |
| `POST /ai/rewrite` | ✅ 注入 |
| `POST /session/expand-episode` | ✅ 注入 |
| `POST /session/generate-outline` | ✅ 注入（辅助大纲方向） |
| `POST /session/answer` | ✅ 注入 |
| `POST /session/summarize` | ✅ 注入（辅助摘要准确性） |
| `POST /ai/global-directive` | ❌ 不注入（执行型，有自己的 prompt） |

### 注入实现方式

修改 `ScriptAIService.__init__`：

```python
class ScriptAIService:
    def __init__(self, ai_config: dict, project_settings: dict | None = None):
        self.ai_config = ai_config
        self.project_settings = project_settings or {}
```

在各 AI 路由实例化时传入 settings：

```python
settings = project.metadata_.get("settings", {}) if project.metadata_ else {}
service = ScriptAIService(project.ai_config, project_settings=settings)
```

注入内容拼入 system prompt 开头（仅注入非空字段）：

```python
def _build_settings_context(self) -> str:
    s = self.project_settings
    lines = ["【剧本设定】"]
    chars = s.get("characters", [])
    if chars:
        lines.append("人物：")
        for c in chars:
            desc = c.get('description') or ''
            if desc:
                lines.append(f"  - {c['name']}：{desc}")
            else:
                lines.append(f"  - {c['name']}")
    if s.get("world_setting"):
        lines.append(f"世界观：{s['world_setting']}")
    if s.get("tone"):
        lines.append(f"风格基调：{s['tone']}")
    if s.get("plot_anchors"):
        lines.append(f"核心要素：{s['plot_anchors']}")
    if s.get("persistent_directive"):
        lines.append(f"持久指令：{s['persistent_directive']}")
    return "\n".join(lines) if len(lines) > 1 else ""
```

---

## 交互流程

### 打开设定抽屉

```
工具栏点击「⚙ 设定」
  → ScriptSettingsDrawer (el-drawer, rtl, :modal="false") 从右侧滑入
  → 覆盖 AI 助手面板区域（AI 面板保持挂载，仅被遮盖）
  → 展示 5 个 el-collapse 折叠面板，从 projectSettings 读取初始值
  → 编辑任意字段 → 全局防抖 500ms 后发送完整 settings
     → PUT /api/v1/drama/{id}/settings
     → 抽屉顶部显示「保存中...」→「已保存」状态
     → 更新 store.projectSettings
```

### 编辑角色

```
点击设定抽屉中角色卡片（如「张三 [编辑]」）
  → CharacterEditOverlay 出现在中央编辑区（半透明遮罩 + 居中卡片）
  → 支持 Esc 关闭（等同取消）、Ctrl+Enter 保存
  → 点击「保存」→ 立即触发 PUT /settings（不等防抖）→ 关闭浮层
  → 点击「取消」→ 放弃修改 → 关闭浮层
```

### AI 自动注入示例

```
【剧本设定】
人物：
  - 张三：性格豪爽，说话直接...
世界观：架空古代，科技与魔法并存...
风格基调：热血励志，节奏快...
核心要素：主角不能死，第三集必须出现背叛...
持久指令：保持角色一致性，不要出现现代词汇...

（以下为原有 system prompt）
...
```

---

## API 设计

### 新增端点

```
PUT /api/v1/drama/{project_id}/settings
```

**权限**：需要登录，且 `project.user_id == current_user.id`（与其他 drama 端点一致）

**Request Body:**
```json
{
  "characters": [{ "id": "string", "name": "string (≤100)", "description": "string (≤2000)" }],
  "world_setting": "string (≤3000)",
  "tone": "string (≤1000)",
  "plot_anchors": "string (≤3000)",
  "persistent_directive": "string (≤2000)"
}
```

**Response:** `200 OK`，返回更新后的 ScriptProject 对象。

**错误响应：**
- `404`：项目不存在
- `403`：无权限
- `422`：字段超出长度限制

**实现逻辑：**
```python
# 仅更新 metadata_["settings"]，保留其他 metadata_ 字段
project.metadata_ = {**(project.metadata_ or {}), "settings": settings.model_dump()}
```

**读取方式（前端）：** 通过现有 `GET /drama/{id}` 返回的 project 对象中 `metadata_["settings"]` 读取，无需独立 GET 端点。

---

## UI 布局

```
┌─ 工作台工具栏 ────────────────────────────────────────────┐
│  [项目名]        [⚙ 设定] [全局指令] [AI助手开关] [...]    │
└──────────────────────────────────────────────────────────┘

┌─ 三列工作区 ──────────────────────────────────────────────┐
│ 大纲树(240px) │ 编辑器(flex) │ AI助手面板(320px)           │
└──────────────────────────────────────────────────────────┘

设定抽屉打开时（el-drawer rtl, :modal="false"，宽360px）：
┌─────────────────────────────┐
│  ⚙ 剧本设定  [已保存 ✓]  ✕  │
├─────────────────────────────┤
│ ▼ 👤 人物设定               │
│  ┌──────────────────────┐  │
│  │ 张三          [编辑] │  │  ← 点击触发 CharacterEditOverlay
│  │ 李四          [编辑] │  │
│  └──────────────────────┘  │
│  [+ 添加角色]               │
├─────────────────────────────┤
│ ▶ 🌍 世界观 / 背景          │
├─────────────────────────────┤
│ ▶ 🎭 风格 / 基调            │
├─────────────────────────────┤
│ ▶ 📌 核心剧情要素           │
├─────────────────────────────┤
│ ▶ ⚡ 持久化 AI 指令         │
└─────────────────────────────┘
```

---

## 范围说明

### 在范围内
- ScriptSettingsDrawer 和 CharacterEditOverlay 两个新组件
- DramaWorkbenchView 工具栏增加「⚙ 设定」按钮
- Pinia store 增加 settings 状态和 action
- 后端新增 PUT /settings 端点
- ScriptAIService 增加 project_settings 参数和注入逻辑
- 5 个受影响 AI 端点传入 project_settings

### 不在范围内
- GlobalDirectiveDialog 任何改动（完整保留）
- 设定版本历史
- 设定模板库
- 人物关系图谱
- 跨项目设定共享
