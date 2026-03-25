# 小说/剧本扩写模块设计文档

**日期**: 2026-03-25
**状态**: 已确认
**模块**: expansion

---

## 1. 概述

### 1.1 目标

构建一个独立的通用扩写模块，支持导入外部文本（.txt/.md/.docx）或从平台内小说/剧本项目导入内容，通过 AI 对原文进行不同程度的扩写。

### 1.2 核心特性

- **独立模块**：完整的 CRUD、独立数据模型和前端视图
- **混合扩写模式**：单段快速扩写 + 整章/整项目批量扩写
- **三级扩写深度**：润色(light) / 中度扩展(medium) / 深度扩写(deep)，可结合目标字数
- **智能分段**：AI 建议分段方案，用户可调整后确认执行
- **文风保持**：AI 自动分析文风画像 + 用户可手动调整
- **灵活交互**：全自动 / 逐段确认 / 随时暂停继续
- **版本对比**：保留原文与扩写后两版，支持并排对比
- **平台打通**：扩写结果可转为小说项目或剧本项目

### 1.3 输入限制

- 最大输入：30,000 字
- 支持格式：.txt / .md / .docx
- 支持来源：文件上传、平台小说章节导入、平台剧本项目导入、手动输入

---

## 2. 数据模型

### 2.1 ExpansionProject（扩写项目）

```python
class ExpansionProject(Base):
    __tablename__ = "expansion_projects"

    id: Mapped[int]                    # PK
    user_id: Mapped[int]               # FK → users
    title: Mapped[str]                 # 项目名称
    source_type: Mapped[str]           # "upload" | "novel" | "drama" | "manual"
    source_ref: Mapped[dict | None]    # {"project_id": 123, "chapter_ids": [1,2]} 或 null
    original_text: Mapped[str]         # 原始全文（纯文本，解析后存储）
    word_count: Mapped[int]            # 原文字数

    # AI 分析结果
    summary: Mapped[str | None]        # 全文摘要（人物、设定、情节线）
    style_profile: Mapped[dict | None] # 文风画像 JSON

    # 扩写配置
    expansion_level: Mapped[str]       # "light" | "medium" | "deep"
    target_word_count: Mapped[int | None]  # 用户设定的目标字数
    style_instructions: Mapped[str | None] # 用户自定义文风调整指令
    ai_config: Mapped[dict | None]     # {"provider", "model", "temperature", ...}

    # 状态管理
    status: Mapped[str]                # "created" → "analyzed" → "segmented" → "expanding" → "paused" → "completed"
    execution_mode: Mapped[str]        # "auto" | "step_by_step"

    metadata: Mapped[dict | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### 2.2 ExpansionSegment（扩写分段）

```python
class ExpansionSegment(Base):
    __tablename__ = "expansion_segments"

    id: Mapped[int]                    # PK
    project_id: Mapped[int]            # FK → expansion_projects
    sort_order: Mapped[int]            # 排序顺序
    title: Mapped[str | None]          # 段落标题/标识

    # 内容版本
    original_content: Mapped[str]      # 原文内容
    expanded_content: Mapped[str | None]  # 扩写后内容

    # 段落级配置（可覆盖项目级）
    expansion_level: Mapped[str | None]    # 覆盖项目级扩写深度
    custom_instructions: Mapped[str | None]  # 该段特殊扩写指令

    # 状态
    status: Mapped[str]                # "pending" | "expanding" | "completed" | "skipped"

    original_word_count: Mapped[int]
    expanded_word_count: Mapped[int | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### 2.3 状态机

```
ExpansionProject:
  created → analyzed → segmented → expanding ⇄ paused → completed
                                       ↑                    |
                                       +-----(重新扩写)------+

ExpansionSegment:
  pending → expanding → completed
    ↑                      |
    +----(重新扩写)---------+
  pending → skipped
```

---

## 3. API 设计

### 3.1 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/expansion/` | 创建扩写项目（手动输入文本） |
| `POST` | `/expansion/upload` | 上传文件创建项目（.txt/.md/.docx） |
| `POST` | `/expansion/import` | 从平台项目导入（小说章节/剧本节点） |
| `GET` | `/expansion/` | 获取项目列表（分页、筛选） |
| `GET` | `/expansion/{id}` | 获取项目详情 |
| `PUT` | `/expansion/{id}` | 更新项目配置 |
| `DELETE` | `/expansion/{id}` | 删除项目 |

### 3.2 分析阶段（SSE 流式）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/expansion/{id}/analyze` | AI 分析全文：生成摘要 + 文风画像 + 分段建议 |

SSE 流事件序列：
```
{"type": "status", "step": "summary"}      → 开始生成摘要
{"type": "text", "text": "..."}            → 摘要内容流式输出
{"type": "status", "step": "style"}        → 开始分析文风
{"type": "text", "text": "..."}            → 文风分析流式输出
{"type": "status", "step": "segmentation"} → 开始分段
{"type": "segments", "data": [...]}        → 分段结果（JSON）
{"type": "done"}                           → 分析完成
```

### 3.3 分段管理

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/expansion/{id}/segments` | 获取所有分段 |
| `PUT` | `/expansion/{id}/segments/{seg_id}` | 编辑分段 |
| `POST` | `/expansion/{id}/segments/split` | 拆分一个分段为两个 |
| `POST` | `/expansion/{id}/segments/merge` | 合并相邻分段 |
| `PUT` | `/expansion/{id}/segments/reorder` | 重新排序 |

### 3.4 扩写执行（SSE 流式）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/expansion/{id}/expand` | 启动批量扩写 |
| `POST` | `/expansion/{id}/segments/{seg_id}/expand` | 扩写单个分段 |
| `POST` | `/expansion/{id}/pause` | 暂停批量扩写 |
| `POST` | `/expansion/{id}/resume` | 恢复批量扩写 |
| `POST` | `/expansion/{id}/segments/{seg_id}/retry` | 重新扩写某段 |

批量扩写 SSE 事件序列：
```
# 对每个 pending 分段：
{"type": "segment_start", "segment_id": 1, "title": "..."}
{"type": "text", "text": "..."}
{"type": "segment_done", "segment_id": 1, "word_count": 1500}

# 逐段模式下：
{"type": "await_confirm", "segment_id": 1}  → 等待用户确认
# 用户调用 POST /expansion/{id}/resume 继续

# 全部完成：
{"type": "done", "total_word_count": 15000}
```

### 3.5 导出与转换

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/expansion/{id}/export?format=txt\|md\|docx&version=original\|expanded\|both` | 导出 |
| `POST` | `/expansion/{id}/convert` | 转为小说项目或剧本项目 `{"target": "novel"\|"drama"}` |

### 3.6 暂停/恢复实现

基于**任务状态 + 多次 SSE 请求**，不引入 WebSocket：
- `POST /expand` 开始扩写，SSE 流式返回
- 暂停：前端 abort SSE 连接 + `POST /pause` 更新项目状态
- 恢复：`POST /resume` → 后端从第一个 pending 段继续，新的 SSE 流

---

## 4. AI 服务设计

### 4.1 ExpansionAIService

```python
class ExpansionAIService:
    async def analyze_text(project) -> AsyncGenerator:
        """一次调用完成：摘要 + 文风画像 + 分段建议"""

    async def expand_segment(project, segment) -> AsyncGenerator:
        """扩写单个分段，携带摘要+文风上下文"""
```

### 4.2 扩写 Prompt 上下文组装

每次扩写单个分段时的 context 结构：

```
┌─────────────────────────────────────────────┐
│ System Prompt                                │
│ ├─ 角色定义：你是专业的小说/剧本扩写专家       │
│ ├─ 文风画像：{style_profile}                  │
│ ├─ 用户文风调整指令：{style_instructions}      │
│ └─ 扩写深度说明：{expansion_level_description} │
│ └─ 剧本标记保留指令（如适用）                  │
├─────────────────────────────────────────────┤
│ User Prompt                                  │
│ ├─ 全文摘要：{summary}                       │
│ ├─ 当前段落位置：第 {n}/{total} 段            │
│ ├─ 前一段扩写结尾（最后200字）：{prev_tail}    │
│ ├─ 当前段原文：{original_content}             │
│ ├─ 后一段开头（前200字）：{next_head}          │
│ ├─ 段落特殊指令：{custom_instructions}        │
│ └─ 目标字数：约 {target_words} 字             │
└─────────────────────────────────────────────┘
```

**关键规则**：
- 摘要控制在 1500 字以内
- 前段已完成扩写时，用扩写版尾部而非原文尾部
- 目标字数根据 expansion_level 和全局目标按比例分配

**剧本标记保留指令**（当检测到原文含剧本格式时自动注入）：
```
如果原文包含剧本格式标记（如 OS、△、【】、角色对话格式等），
扩写时必须保留这些标记的格式和含义，不得将其转化为普通叙述。
扩写可以增加新的标记使用，但必须遵循原文的标记体系。
```

### 4.3 扩写深度定义

```python
EXPANSION_LEVELS = {
    "light": {
        "description": "润色补充：保持原有结构不变，补充感官细节、环境描写、"
                       "人物微表情。不增加新情节或新对话。",
        "multiplier": 1.5,
    },
    "medium": {
        "description": "中度扩展：在原有框架内增加过渡段落、内心独白、场景描写、"
                       "对话细节。可适当展开已有情节但不引入新支线。",
        "multiplier": 2.5,
    },
    "deep": {
        "description": "深度扩写：大幅丰富内容，可增加子场景、展开人物互动、"
                       "补充背景故事、增加伏笔和细节呼应。保持主线不变的前提下"
                       "充分展开叙事空间。",
        "multiplier": 4.0,
    },
}
```

### 4.4 分析阶段 Prompt

输入完整原文（3w字以内），输出结构化 JSON：

```json
{
  "summary": "结构化摘要...",
  "style_profile": {
    "narrative_pov": "第三人称有限视角",
    "tone": "沉郁压抑，偶有黑色幽默",
    "sentence_style": "长短句交替，善用排比",
    "vocabulary": "偏书面语，古风词汇较多",
    "rhythm": "节奏偏慢，重描写轻对话",
    "notable_features": "喜用通感手法，色彩意象丰富"
  },
  "segments": [
    {"title": "开篇：主角出场", "start_marker": "第一句话...", "end_marker": "...最后一句", "word_count": 2300},
    ...
  ]
}
```

### 4.5 Token 预算分析

- **分析阶段**：3w 字 ≈ 15k-20k tokens 输入，摘要+分析输出 ≈ 2k-3k tokens。主流模型 128k-200k context，无压力。
- **扩写阶段**：每段原文 2000-5000 字，deep 模式 4x 后最大约 20000 字 ≈ 10k-13k tokens 输出。GPT-4o 16k / Claude 8k-64k 输出上限内。
- **超限处理**：如预估某段扩写结果超出模型输出上限，服务层自动将该段再拆分为子段。

### 4.6 AI 输出截断续写

```python
async def expand_segment_with_continuation(project, segment):
    """带自动续写的扩写"""
    full_text = ""

    # 第一次扩写
    async for chunk in expand_segment(project, segment):
        full_text += chunk
        yield chunk

    # 检测是否被截断
    if is_truncated(full_text):
        continuation_prompt = f"你之前的扩写在此处被截断，请从断点继续：\n...{full_text[-500:]}"
        async for chunk in continue_expansion(project, segment, continuation_prompt):
            full_text += chunk
            yield chunk

    # 最多续写 2 次，超过则标记警告

def is_truncated(text: str) -> bool:
    """启发式判断输出是否被截断"""
    text = text.strip()
    normal_endings = ['。', '！', '？', '"', '」', '】', '……', '——']
    if any(text.endswith(e) for e in normal_endings):
        return False
    return True
```

### 4.7 Provider 复用

完全复用已有 `providers/` 架构（OpenAI / Anthropic / Ollama），通过 `ai_config` 选择。

---

## 5. 文件解析与转换

### 5.1 文件解析器

```python
class FileParser:
    @staticmethod
    async def parse(file: UploadFile) -> ParseResult:
        """根据文件扩展名分派解析"""

    @staticmethod
    def parse_txt(content: bytes) -> str:
        """纯文本：检测编码(utf-8/gbk/gb2312)"""

    @staticmethod
    def parse_markdown(content: bytes) -> str:
        """Markdown：去除格式标记，保留文本结构"""

    @staticmethod
    def parse_docx(content: bytes) -> str:
        """Word：使用 python-docx 提取段落文本"""

class ParseResult:
    text: str
    word_count: int
    detected_structure: list  # 标题、章节分隔等结构标记
```

依赖：`python-docx`

### 5.2 平台项目导入

```python
# 从小说项目导入
async def import_from_novel(project_id, chapter_ids, db, user):
    """读取指定章节，按顺序拼接，章节间用 \n\n---\n\n 分隔，保留章节标题"""

# 从剧本项目导入
async def import_from_drama(project_id, db, user):
    """复用 drama 模块已有的 export 序列化逻辑"""
```

### 5.3 导出

```python
async def export_expansion(project, segments, format, version):
    """
    format: txt | md | docx
    version: original | expanded | both
    both 模式：每段先显示原文（标注），再显示扩写内容
    """
```

### 5.4 转为剧本项目

```python
async def convert_to_drama(expansion_project, db):
    """
    1. 检测原文中的剧本格式标记（OS、△、【】、角色名：等）
    2. 如果检测到剧本格式 → 解析标记，映射为 ScriptNode 类型：
       - OS/（OS）→ inner_voice
       - △ → action
       - 【...】→ effect
       - 角色名：对话内容 → dialogue（speaker + content）
       - 场景标题（xx 日/内）→ scene
       - 其余叙述内容 → narration
    3. 如果未检测到剧本格式 → 每段作为 narration 节点
    """
```

### 5.5 转为小说项目

```python
async def convert_to_novel(expansion_project, db):
    """创建 Project + Chapters，每个 segment 的 expanded_content → 一个 Chapter"""
```

---

## 6. 前端架构

### 6.1 页面结构

| 视图 | 路由 | 说明 |
|------|------|------|
| `ExpansionListView` | `/expansion` | 项目列表，创建入口 |
| `ExpansionCreateView` | `/expansion/create` | 创建项目（上传/导入/手动输入） |
| `ExpansionAnalyzeView` | `/expansion/analyze/:id` | 分析结果 + 分段调整 + 参数配置 |
| `ExpansionWorkbenchView` | `/expansion/workbench/:id` | 扩写工作台（核心页面） |

### 6.2 工作台布局（三栏）

```
┌──────────────┬────────────────────────────────────┬──────────────┐
│  分段导航     │         内容对比区                   │  控制面板     │
│              │                                     │              │
│  ■ 第1段 ✓   │  ┌─原文──────┐  ┌─扩写结果────┐    │  扩写深度     │
│  ■ 第2段 ✓   │  │           │  │             │    │  ○ 润色       │
│  ► 第3段 ⟳   │  │  原始内容  │  │  扩写内容    │    │  ● 中度       │
│  ■ 第4段 ·   │  │           │  │  (流式显示)  │    │  ○ 深度       │
│  ■ 第5段 ·   │  │           │  │             │    │              │
│              │  └───────────┘  └─────────────┘    │  目标字数     │
│              │                                     │  [____] 字    │
│  ──────────  │  字数: 1200 → 2850 (+137%)         │              │
│  进度: 2/5   │                                     │  文风调整     │
│  总字数:     │                                     │  [更口语化..] │
│  5000→12000  │                                     │              │
│              │                                     │  [扩写此段]   │
│              │                                     │  [全部扩写]   │
│              │                                     │  [暂停/继续]  │
└──────────────┴────────────────────────────────────┴──────────────┘
```

### 6.3 组件

```
src/components/expansion/
├── ExpansionSegmentList.vue    # 左栏：分段导航，状态图标，进度统计
├── ExpansionComparePanel.vue   # 中栏：原文 vs 扩写并排对比
├── ExpansionControlPanel.vue   # 右栏：扩写参数、操作按钮
├── ExpansionProgressBar.vue    # 批量扩写进度条
├── SegmentSplitDialog.vue      # 拆分/合并分段弹窗
├── StyleProfileCard.vue        # 文风画像展示卡片
├── ImportSourceDialog.vue      # 从平台项目导入选择弹窗
└── ExportConvertDialog.vue     # 导出/转换弹窗
```

### 6.4 创建页面

三种导入方式：上传文件（拖拽区域）、从项目导入（选择弹窗）、手动输入（文本框）。

### 6.5 分析页面工作流

1. 进入页面 → 自动触发 `/analyze` API
2. 流式展示：摘要逐字出现 → 文风画像逐项填充 → 分段列表出现
3. 用户可：查看/编辑摘要、查看文风画像、调整分段（拆分/合并）、设置扩写参数
4. 确认后跳转 WorkbenchView

### 6.6 Pinia Store

```typescript
interface ExpansionState {
  projects: ExpansionProject[]
  currentProject: ExpansionProject | null
  segments: ExpansionSegment[]
  currentSegmentId: number | null
  isAnalyzing: boolean
  isExpanding: boolean
  expandingSegmentId: number | null
}

// 核心 actions:
// 项目: fetchProjects, createProject, uploadProject, importProject, fetchProject, updateProject, removeProject
// 分析: startAnalysis
// 分段: fetchSegments, updateSegment, splitSegment, mergeSegments, reorderSegments
// 扩写: expandSegment, expandAll, pauseExpansion, resumeExpansion, retrySegment
// 导出: exportProject, convertProject
```

---

## 7. 错误处理与边界情况

### 7.1 文件上传

| 场景 | 处理 |
|------|------|
| 超过 30000 字 | 400，提示裁剪 |
| 编码无法识别 | 尝试 utf-8 → gbk → gb2312，均失败则 400 |
| docx 含图片/表格 | 忽略非文本内容，返回警告 |
| 空文件 | 400 |
| 格式与扩展名不匹配 | 400 |

### 7.2 扩写过程

| 场景 | 处理 |
|------|------|
| AI 调用失败 | 当前段 → pending，项目 → paused，返回 error 事件 |
| AI 输出截断 | 自动续写（最多 2 次），仍不完整则标记警告 |
| 连接断开 | 停止后续段落，已完成段保留，项目 → paused |
| 重复提交扩写 | 409 Conflict（同一项目同一时间只允许一个扩写任务） |

---

## 8. 技术栈与依赖

### 后端新增

```
backend/app/models/expansion.py
backend/app/schemas/expansion.py
backend/app/routers/expansion.py
backend/app/services/expansion_ai_service.py
backend/app/services/file_parser.py
backend/scripts/migrate_add_expansion.py
```

新增 Python 依赖：`python-docx`

### 前端新增

```
frontend/src/views/ExpansionListView.vue
frontend/src/views/ExpansionCreateView.vue
frontend/src/views/ExpansionAnalyzeView.vue
frontend/src/views/ExpansionWorkbenchView.vue
frontend/src/components/expansion/  (8 个组件)
frontend/src/stores/expansion.ts
frontend/src/api/expansion.ts
```

### 复用现有模块

- Provider 抽象层（`providers/`）
- SSE 流式架构
- 用户认证与数据隔离
- AI 配置系统
- 前端 SSE 请求工具（`_streamRequest` 模式）
