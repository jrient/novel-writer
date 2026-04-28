# Handbook 驱动的剧本创作优化设计

> 日期: 2026-04-17
> 状态: 待实施

## 背景

`script_rubric` pipeline 基于 44 部剧本 + 11 名编辑的评审数据，提炼了包含通用规律、类型专项、地雷清单、校准刻度的评审手册（handbook）。手册 v4 在分数校准上表现优秀（MAE 2.4），积累了大量可用于指导创作的结构化知识。

当前剧本创作模块（drama）的 AI prompts 是通用模板，完全没有利用 rubric 手册中的知识。本设计将手册知识注入创作全流程，提升 AI 辅助创作的质量。

## 设计决策总结

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 知识覆盖阶段 | 全流程贯穿 | 每个阶段都能从手册知识中获益 |
| 注入方式 | 混合方案 | 通用规律+地雷清单静态嵌入，类型专项按题材动态加载 |
| 手册版本管理 | 文件引用 | 运行时读最新版本，pipeline 重跑后自动生效 |
| 问答阶段 | 增加类型专项槽位 | 通用 5 槽位后追加 1-2 个类型针对性问题 |
| 地雷清单使用 | 预防+兜底 | prompt 注入做预防，生成后独立检查做兜底 |
| 维度评估暴露 | 用户主动触发 | 新增 AI 评审按钮，按需调用，不打断创作流程 |
| 摘要结构 | 通用+类型专项字段 | 动态追加 genre_extras 确保类型信息传递到下游 |

## 架构总览

```
script_rubric/outputs/handbook/handbook_vN.md  (最新版本文件)
                    │
             HandbookProvider  ← 启动时加载，按标题层级解析为结构化片段
                    │
   ┌────────────────┼────────────────────────────────┐
   │                │                                │
   ▼                ▼                                ▼
问答阶段         大纲/内容创作阶段                 AI 评审
(类型专项槽位)   (地雷预防+维度注入+兜底检查)    (全量手册+7维度评分)
   │                │                                │
   ▼                ▼                                ▼
摘要阶段         ScriptNode                      评审结果JSON
(genre_extras)   (内容质量提升)                   (用户按需触发)
```

## 第一部分：HandbookProvider 服务层

### 新增文件

`backend/app/services/handbook_provider.py`

### 职责

1. 从 `script_rubric/outputs/handbook/` 目录自动发现并加载最新版本的 handbook markdown
2. 将 markdown 按标题层级解析为结构化片段（通用规律、类型专项、地雷清单、校准刻度）
3. 提供按 `(阶段, 类型)` 检索的接口，返回裁剪后的文本片段供 prompt 注入

### 核心接口

```python
class HandbookProvider:
    def __init__(self, handbook_dir: str = None):
        """加载最新版本的 handbook"""

    @property
    def version(self) -> str:
        """当前加载的版本号，如 'v4'"""

    def get_universal_rules(self, dimensions: list[str] = None) -> str:
        """获取通用规律（可选过滤维度）"""

    def get_genre_overlay(self, source_type: str, genre: str) -> str | None:
        """获取类型专项（如 '原创/萌宝'），无匹配返回 None"""

    def get_red_flags(self) -> str:
        """获取地雷清单全文"""

    def get_calibration(self) -> str:
        """获取校准刻度表"""

    def get_question_slots(self, source_type: str, genre: str) -> list[dict]:
        """获取类型专项的额外问答槽位"""

    def get_summary_extra_fields(self, source_type: str, genre: str) -> list[dict]:
        """获取类型专项的额外摘要字段定义"""
```

### Markdown 解析策略

Handbook 结构固定为 4 大部分：
- `## 第一部分：通用规律` → 按 `### N. dimension_key` 二级切分
- `## 第二部分：类型专项` → 按 `### 原创 / 萌宝` 等标题切分
- `## 第三部分：地雷清单` → 整段提取
- `## 第四部分：评分校准刻度` → 整段提取

用正则按 `##` / `###` 标题分段，不需要复杂的 markdown parser。

### 缓存与更新

- 启动时加载一次，缓存在内存中
- 提供 `reload()` 方法，handbook pipeline 重跑后可手动触发或重启服务生效
- 不做热更新，重启即可

## 第二部分：问答阶段增强

### 改动概述

在通用 5 槽位完成后，根据检测到的类型追加 1-2 个针对性问题。

### 类型检测时机

- 通用 5 槽位完成后，调用 `HandbookProvider.get_genre_overlay(source_type, genre)` 检查匹配
- 类型信息从用户的 concept 和回答中由 AI 推断
- 如果匹配到类型专项，从 `get_question_slots()` 获取追加槽位

### 类型专项槽位示例（萌宝类）

```
通用槽位 1-5（不变）
  ↓
类型检测：匹配到「原创/萌宝」
  ↓
追加槽位6：萌宝的核心设定是什么？有什么区别于常规奶团子的反差特点？
追加槽位7：男主/父亲角色什么时候出场？和萌宝的第一次互动是什么场景？
```

### prompt 改动

在 `ScriptAIService.generate_question()` 中，当检测到已完成通用 5 槽位时：
- system prompt 追加类型专项上下文（从 HandbookProvider 获取）
- user prompt 指示 AI 针对类型专项槽位提问
- 追加槽位全部完成或用户跳过后，进入摘要阶段

### 不变的部分

- 通用 5 槽位的 prompt 内容不变
- 会话状态机不变（init → collecting → generating → done）
- 前端问答 UI 不变
- 用户随时可跳过追加槽位

## 第三部分：摘要阶段增强

### 改动概述

`generate_summary()` 根据类型动态追加专项字段，确保类型关键信息结构化传递到下游。

### 动态摘要结构

以萌宝类为例，摘要输出变为：

```json
{
  "故事概要": "...",
  "主要角色": ["..."],
  "核心冲突": "...",
  "场景设定": "...",
  "风格基调": "...",
  "目标集数": 20,
  "genre_tag": "原创/萌宝",
  "genre_extras": {
    "萌宝核心设定": "魔丸转世，好赌海量，区别于常规乖巧奶团子",
    "父母角色定位": "男主第2集出场，初次互动为宿命绑定场景"
  }
}
```

### Schema 变更

`SessionSummaryResponse` 新增两个可选字段：

```python
class SessionSummaryResponse(BaseModel):
    # ... 现有 6 个字段不变 ...
    genre_tag: Optional[str] = Field(None, description="匹配到的类型标签")
    genre_extras: Optional[Dict[str, str]] = Field(None, description="类型专项信息")
```

### 下游传递

摘要中的 `genre_tag` 和 `genre_extras` 在后续阶段自动传递：
- 大纲生成：prompt 中包含类型专项信息
- 内容创作：`_build_node_context()` 中包含类型专项上下文
- AI 评审：评审时参考类型专项的加权/降权建议

### 前端兼容

- `genre_extras` 是可选字段，前端摘要编辑页面可原样展示为可编辑的 key-value 对
- 没有匹配到类型专项时，这两个字段为 null，行为与当前完全一致

## 第四部分：大纲生成增强

### Prompt 注入（预防层）

`generate_outline()` 的 system prompt 增加两段来自 HandbookProvider 的内容：

```
原有 system prompt
  +
【评审手册·地雷清单】          ← get_red_flags()，精简为条目列表
以下是编辑常见拒稿原因，生成大纲时必须规避：
- 开局平淡无冲突钩子
- 男主出场超过第3集
- ...

【评审手册·维度要点】          ← get_universal_rules()，精简为每维度1-2句核心规律
生成大纲时请确保：
- 题材创新：避免纯套路，需有至少一个反差元素
- 开局钩子：第1集必须有强情绪事件
- ...
```

如果摘要中有 `genre_tag`，追加类型专项：
```
【类型专项·原创/萌宝】        ← get_genre_overlay()
- 萌宝人设必须有反差特点
- 父/母角色不能沦为背景板
- ...
```

### 大纲地雷检查（兜底层）

新增 `ScriptAIService.check_outline_red_flags()` 方法：

```python
async def check_outline_red_flags(
    self, outline: dict, genre_tag: str | None
) -> list[dict]:
    """
    对生成的大纲做独立地雷检查
    返回: [{"flag": "男主出场过晚", "severity": "warning",
            "detail": "男主在第5集才出现", "suggestion": "建议调整到第1-2集"}]
    """
```

- 在 `session_generate_outline` 路由中，大纲保存后自动调用
- 检查结果通过 SSE 以 `type: "red_flag_warnings"` 事件返回
- 不阻断流程，用户看到警告后自行决定是否调整

### SSE 事件流变化

```
data: {"type": "text", "text": "..."}                    ← 大纲内容流
data: {"type": "partial_warning", ...}                   ← 已有的集数不完整警告
data: {"type": "red_flag_warnings", "flags": [...]}      ← 新增：地雷检查结果
data: {"type": "done"}
```

### 展开场景阶段

`expand_episode()` 的 system prompt 同样注入维度要点和地雷清单（精简版）。不做独立检查。

## 第五部分：内容创作阶段增强

### system prompt 增强

`expand_node()` / `rewrite_content()` 的 system prompt 追加精简版维度要点，只注入与内容创作直接相关的维度：

```
原有 system prompt
  +
【创作参考·维度要点】
- 文笔台词：对白需自然流畅、符合人物性格，避免书面化表述
- 节奏冲突：每个场景至少一个微冲突推动，避免纯铺垫无事件
- 爽点兑现：承诺的爽点必须在合理节拍内兑现，不可无限延迟
- 人设立体度：角色行为需符合已建立的性格，避免为剧情强行降智
```

不注入题材创新和对标差异化（宏观维度，不适合单节点级别）。

### 类型专项上下文传递

`_build_node_context()` 扩展为读取 `genre_tag` 和 `genre_extras`：

```python
# 新增
if summary.get("genre_tag"):
    parts.append(f"类型标签：{summary['genre_tag']}")
if summary.get("genre_extras"):
    for k, v in summary["genre_extras"].items():
        parts.append(f"{k}：{v}")
```

### global_directive 不做额外注入

全局指令是用户主动的自由指令，强行注入手册规律可能与用户意图冲突，保持原样。

## 第六部分：AI 评审功能（新增）

### 新增 API

```
POST /api/v1/drama/{id}/ai/review
```

请求体：无（评审整个项目当前内容）

响应：SSE 流式，最终输出结构化 JSON：

```json
{
  "overall_score": 78,
  "status_suggestion": "改",
  "dimension_scores": {
    "premise_innovation": {"score": 7, "comment": "穿越+复仇有一定新意，但缺少差异化亮点"},
    "opening_hook": {"score": 8, "comment": "第1集冲突强烈，钩子有效"},
    "character_depth": {"score": 6, "comment": "女主形象清晰，男主偏脸谱化"},
    "pacing_conflict": {"score": 5, "comment": "第3-5集节奏拖沓，支线过多"},
    "writing_dialogue": {"score": 7, "comment": "对白自然，但部分场景书面化"},
    "payoff_satisfaction": {"score": 6, "comment": "前10集爽点兑现及时，中段有滞后"},
    "benchmark_differentiation": {"score": 6, "comment": "与同类作品相似度较高，需强化差异点"}
  },
  "red_flags_hit": ["第3-5集节奏拖沓，无实质冲突推动"],
  "green_flags_hit": ["开局钩子强烈", "萌宝设定有反差感"],
  "top_suggestions": [
    "第4集建议删除支线，聚焦主线冲突",
    "男主需要在第6集前展现性格弧光",
    "第8集爽点可提前到第7集兑现"
  ]
}
```

### 实现逻辑

```python
async def review_script(self, script_type, title, content, genre_tag) -> AsyncGenerator:
    """
    prompt 构成：
    1. system: 手册全文（通用规律 + 类型专项 + 地雷清单 + 校准刻度）
    2. user: 当前剧本全部节点内容 + 输出格式要求

    复用 backtest_predict.md 的评审逻辑，面向创作中的草稿
    """
```

- 读取全部节点内容（复用 global_directive 中已有的节点收集逻辑）
- system prompt 注入完整手册（唯一需要全量注入的场景）
- 如果有 `genre_tag`，追加类型专项的加权/降权建议

### 路由

在 `drama.py` 新增路由：

```python
@router.post("/{id}/ai/review")
async def review_script(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """AI 评审（SSE 流式）"""
```

### 不做的部分

- 不自动触发评审（成本高，手册全量注入 token 多）
- 不存储评审历史（评审结果是即时参考，不入库）
- 不阻断任何创作流程

## 各阶段 Prompt 注入策略汇总

| 阶段 | 注入内容 | 来源方法 | 注入量 |
|------|---------|---------|--------|
| 问答（通用） | 无变化 | - | - |
| 问答（追加） | 类型专项上下文 | `get_genre_overlay()` | 精简 |
| 摘要生成 | 类型专项字段定义 | `get_summary_extra_fields()` | 精简 |
| 大纲生成 | 地雷清单 + 维度要点 + 类型专项 | `get_red_flags()` + `get_universal_rules()` + `get_genre_overlay()` | 中等 |
| 大纲检查 | 地雷清单 + 类型专项 | `get_red_flags()` + `get_genre_overlay()` | 中等 |
| 展开场景 | 维度要点 + 地雷清单（精简） | `get_universal_rules()` + `get_red_flags()` | 精简 |
| 展开/重写节点 | 创作相关维度（4个） + 类型上下文 | `get_universal_rules(dimensions=[...])` | 精简 |
| 全局指令 | 无变化 | - | - |
| AI 评审 | 手册全文 | 全部方法 | 全量 |

## 涉及文件变更

### 新增
- `backend/app/services/handbook_provider.py` — HandbookProvider 服务层

### 修改
- `backend/app/services/script_ai_service.py` — 各生成方法注入手册知识 + 新增 review/check 方法
- `backend/app/routers/drama.py` — 新增 `/ai/review` 路由 + 大纲检查 SSE 事件
- `backend/app/schemas/drama.py` — SessionSummaryResponse 新增 genre_tag/genre_extras

### 不变
- 前端问答/编辑 UI（追加问题与通用问题展现一致）
- 大纲 JSON 结构（sections/children）
- 会话状态机
- ScriptNode / ScriptSession 数据模型
- confirm-outline 写入逻辑

## 前端影响（最小化）

1. **摘要编辑页**：genre_extras 为可选 key-value 对，展示即可
2. **大纲页面**：新增地雷警告提示组件（接收 `red_flag_warnings` SSE 事件）
3. **编辑器**：新增"AI 评审"按钮，展示评审结果弹窗/侧栏
