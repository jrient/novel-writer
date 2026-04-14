# 设计规格：技术债优化第 1 轮 — SSE 重构 + Prompt 外置 + AiPanel 拆分

**日期：** 2026-04-14
**功能：** 通过三个关联重构项，消除核心技术债、降低维护成本
**状态：** 待实现
**范围：** 后端 AI 路由层 + AI 服务层 + 前端 AI 面板组件

---

## 背景

`novel-writer` 进入 v1.2.0 后，在多轮功能迭代中积累了若干技术债，本轮优化聚焦 **三个最大痛点**：

1. **SSE 流式逻辑严重重复**：`backend/app/routers/ai.py` 文件膨胀至 847 行，其中三处 SSE 端点（`ai_generate`、`extract_characters`、`batch_generate`）各自重复了 ~60 行相同的心跳+超时+token 收集逻辑。任何 SSE 行为的修改都需要同步 3+ 处，极易遗漏。

2. **Prompt 模板硬编码在 Python 代码中**：`backend/app/services/ai_service.py` 前 ~300 行全是 `PROMPTS` 字典，包含 17 个大段中文 prompt。prompt 的版本管理、diff 阅读、外部编辑均不便。

3. **前端 AiPanel 组件过于臃肿**：`frontend/src/components/AiPanel.vue` 达 1616 行，包含历史记录、模板管理、操作按钮、输出区、上下文预览全部 UI 与逻辑，认知负担高，子功能难以独立演进。

本轮优化不引入新功能，目标是 **让现有代码更可维护、修改更安全**。

---

## 功能范围

### 涉及文件

**方案 A（SSE 重构）**
- 新增 `backend/app/utils/sse.py`（SSEStreamHelper、TokenTracker）
- 新增 `backend/app/routers/ai_generate.py`（拆自 ai.py）
- 新增 `backend/app/routers/ai_batch.py`（拆自 ai.py）
- 新增 `backend/app/routers/ai_config.py`（拆自 ai.py）
- 删除 `backend/app/routers/ai.py`
- 修改 `backend/app/routers/__init__.py`（路由导出调整）
- 修改 `backend/app/main.py`（路由注册调整）

**方案 B（Prompt 外置）**
- 新增 `backend/app/prompts/` 目录下 17 个 `.txt` 文件
- 新增 `backend/app/services/prompt_manager.py`
- 修改 `backend/app/services/ai_service.py`（移除 PROMPTS 字典，改用 PromptManager）
- 修改 `backend/app/services/script_ai_service.py` 和 `expansion_ai_service.py`（如有引用）
- 修改 `backend/app/main.py`（启动时加载 prompts）

**方案 C（AiPanel 拆分）**
- 新增 `frontend/src/components/ai/` 目录
- 新增 `AiPanel.vue`（重写为容器组件）
- 新增 `AiHistoryPanel.vue`、`AiTemplatePanel.vue`、`AiActionBar.vue`、`AiOutputArea.vue`、`AiContextPreview.vue`
- 新增 `frontend/src/composables/useAiGeneration.ts`
- 删除（或清空后重写）`frontend/src/components/AiPanel.vue`
- 修改引用 `AiPanel` 的父组件（主要是 `ContextPanel.vue` / `WorkbenchView.vue`）

### 不涉及

- AI Provider 抽象层（`providers/`）— 保持不变
- 智能上下文服务（`smart_context.py`）— 保持不变
- 数据库模型、路由契约、前端 API 封装 — 保持不变
- Token 使用统计逻辑的业务语义 — 仅形式重构，计费公式不变
- drama / expansion 模块的业务逻辑 — 本轮不动（其 `script_ai_service.py` 和 `expansion_ai_service.py` 若有 SSE 心跳代码，列为后续轮次）

---

## 方案 A：SSE 流式基础设施重构

### A.1 当前重复模式分析

`ai.py` 中三处 SSE 端点的公共模板（简化）：

```python
async def stream_with_heartbeat():
    stream_iter = stream_gen.__aiter__()
    pending_task = None
    heartbeat_count = 0
    yield ": connected\n\n"

    while True:
        try:
            if pending_task is None:
                pending_task = asyncio.create_task(stream_iter.__anext__())
            done, _ = await asyncio.wait([pending_task], timeout=5.0)
            if done:
                sse_line = pending_task.result()
                pending_task = None
                heartbeat_count = 0
                # 收集 text / usage
                if sse_line.startswith("data: "):
                    try:
                        _d = json.loads(sse_line[6:].strip())
                        if _d.get("text"): collected_output.append(_d["text"])
                        if _d.get("usage"): real_usage[0] = _d["usage"]
                    except Exception: pass
                yield sse_line
            else:
                heartbeat_count += 1
                if heartbeat_count > 120:
                    pending_task.cancel()
                    yield f'data: {{"error":"..."}}\n\n'
                    break
                yield ": heartbeat\n\n"
        except StopAsyncIteration:
            break
        except Exception as e:
            yield f'data: {{"error":"..."}}\n\n'
            break

    # 记录 token
    if actual_provider != "demo":
        # ...
        await log_token_usage(...)
```

### A.2 SSEStreamHelper 类设计

文件：`backend/app/utils/sse.py`

```python
"""统一的 SSE 流式响应助手。
避免每个 AI 端点重复编写心跳、超时、异常处理、token 收集逻辑。
"""
import asyncio
import json
import logging
from typing import AsyncGenerator, Callable, Optional

logger = logging.getLogger(__name__)

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def sse_event(data: dict) -> str:
    """构造一条 data: 事件行（自动 JSON 序列化、中文不转义）"""
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_heartbeat() -> str:
    """SSE 注释行（心跳）"""
    return ": heartbeat\n\n"


class SSEStreamHelper:
    """SSE 流式响应助手。

    包装一个原始 AsyncGenerator，自动处理：
    - 初始 ": connected\n\n" 探测
    - 每 heartbeat_interval 秒发送心跳保活
    - 超过 max_heartbeats 次连续无数据则终止（防止永久挂起）
    - 捕获 StopAsyncIteration 正常结束 / 其他异常输出错误 SSE
    - 可选的 on_text / on_usage 回调用于 token 使用统计
    """

    def __init__(
        self,
        heartbeat_interval: float = 5.0,
        max_heartbeats: int = 120,
        error_message: str = "AI 服务处理异常，请稍后再试",
        timeout_message: str = "AI 服务响应超时",
    ):
        self.heartbeat_interval = heartbeat_interval
        self.max_heartbeats = max_heartbeats
        self.error_message = error_message
        self.timeout_message = timeout_message

    async def wrap_stream(
        self,
        stream_gen: AsyncGenerator[str, None],
        on_text: Optional[Callable[[str], None]] = None,
        on_usage: Optional[Callable[[dict], None]] = None,
        preamble: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """包装原始 SSE 生成器。

        Args:
            stream_gen: 原始的产出 "data: ...\n\n" 行的异步生成器
            on_text: 每当流中出现 {"text": "..."} 时的回调
            on_usage: 流中出现 {"usage": {...}} 时的回调
            preamble: 流开始前要发送的额外 SSE 行（如 context_used 事件）
        """
        yield ": connected\n\n"

        if preamble:
            for line in preamble:
                yield line

        stream_iter = stream_gen.__aiter__()
        pending_task: Optional[asyncio.Task] = None
        heartbeat_count = 0

        while True:
            try:
                if pending_task is None:
                    pending_task = asyncio.create_task(stream_iter.__anext__())

                done, _ = await asyncio.wait(
                    [pending_task], timeout=self.heartbeat_interval
                )

                if done:
                    sse_line = pending_task.result()
                    pending_task = None
                    heartbeat_count = 0

                    # 解析并触发回调
                    if sse_line.startswith("data: "):
                        try:
                            payload = json.loads(sse_line[6:].strip())
                            if on_text and payload.get("text"):
                                on_text(payload["text"])
                            if on_usage and payload.get("usage"):
                                on_usage(payload["usage"])
                        except (json.JSONDecodeError, Exception):
                            pass
                    yield sse_line
                else:
                    heartbeat_count += 1
                    if heartbeat_count > self.max_heartbeats:
                        logger.error(
                            f"SSE 超时：已发送 {self.max_heartbeats} 次心跳仍无响应"
                        )
                        pending_task.cancel()
                        yield sse_event({"error": self.timeout_message})
                        break
                    yield sse_heartbeat()

            except StopAsyncIteration:
                break
            except Exception as e:
                logger.error(f"SSE 流异常: {e}", exc_info=True)
                yield sse_event({"error": self.error_message})
                break
```

### A.3 TokenTracker 类设计

```python
class TokenTracker:
    """在 SSE 流结束后自动记录 token 使用。

    使用方式：
        tracker = TokenTracker(db, user_id=..., provider="openai", ...)
        async for line in helper.wrap_stream(stream, on_text=tracker.on_text,
                                              on_usage=tracker.on_usage):
            yield line
        await tracker.flush(input_text=prompt)
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
        provider: str,
        model: str,
        action: str,
        project_id: int,
    ):
        self.db = db
        self.user_id = user_id
        self.provider = provider
        self.model = model
        self.action = action
        self.project_id = project_id
        self._collected_text: list[str] = []
        self._real_usage: Optional[dict] = None

    def on_text(self, text: str) -> None:
        self._collected_text.append(text)

    def on_usage(self, usage: dict) -> None:
        self._real_usage = usage

    async def flush(self, input_text: str = "") -> None:
        """流结束后调用。demo provider 不记录。"""
        if self.provider == "demo":
            return

        if self._real_usage:
            in_tok = self._real_usage.get("input_tokens", 0)
            out_tok = self._real_usage.get("output_tokens", 0)
        else:
            output_text = "".join(self._collected_text)
            in_tok = estimate_tokens(input_text)
            out_tok = estimate_tokens(output_text)

        await log_token_usage(
            db=self.db,
            user_id=self.user_id,
            provider=self.provider,
            model=self.model,
            action=self.action,
            input_tokens=in_tok,
            output_tokens=out_tok,
            project_id=self.project_id,
        )
```

### A.4 路由拆分

**拆分后目录：**

```
backend/app/routers/
├── ai_generate.py   # /api/v1/projects/{id}/ai/generate, /context-preview, /extract_characters
├── ai_batch.py      # /api/v1/projects/{id}/ai/batch-generate
└── ai_config.py     # /api/v1/ai/config（独立前缀）
```

**ai_generate.py 中 ai_generate 端点重构示例（核心逻辑）：**

```python
@router.post("/generate")
async def ai_generate(
    project_id: int,
    payload: AIGenerateRequest,
    project: Project = Depends(get_project_with_auth),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    smart_context = SmartContextService(db, project_id)

    # 章节内容获取（保持原逻辑）
    content = payload.content
    if payload.chapter_id and not content:
        chapter_result = await db.execute(
            select(Chapter).where(
                Chapter.id == payload.chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        if chapter:
            content = chapter.content or ""

    # extract_characters 分支保持独立（prompt 和数据准备逻辑不同）
    if payload.action == "extract_characters":
        return await _handle_extract_characters(
            db=db, payload=payload, project_id=project_id,
            current_user=current_user,
        )

    # 智能上下文
    context_data = await smart_context.build_smart_context(...)
    context_text = context_data.get("context_text", "")
    context_entities = context_data.get("entities", [])

    # plot_enhance 额外上下文（保持原逻辑）
    outline_context, previous_chapters = "", ""
    if payload.action == "plot_enhance":
        outline_context, previous_chapters = await _build_plot_enhance_context(
            db, project_id, payload.chapter_id
        )

    # 确定 provider/model
    actual_provider = AIService._get_available_provider(payload.provider)
    actual_model = _get_model_for_provider(actual_provider)

    # 创建流 + tracker
    stream_gen = AIService.generate_stream(
        action=payload.action,
        content=content,
        provider=payload.provider,
        title=project.title,
        genre=project.genre or "",
        description=project.description or "",
        question=payload.question or "",
        context_text=context_text,
        outline_context=outline_context,
        previous_chapters=previous_chapters,
    )

    helper = SSEStreamHelper()
    tracker = TokenTracker(
        db=db, user_id=current_user.id,
        provider=actual_provider, model=actual_model,
        action=payload.action, project_id=project_id,
    )

    # 前置 context_used 事件
    preamble = []
    if context_entities:
        preamble.append(sse_event({
            "type": "context_used", "entities": context_entities,
        }))

    async def response_stream():
        async for line in helper.wrap_stream(
            stream_gen,
            on_text=tracker.on_text,
            on_usage=tracker.on_usage,
            preamble=preamble,
        ):
            yield line
        await tracker.flush(input_text=content or "")

    return StreamingResponse(
        response_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
```

**端点 URL、入参、出参 SSE 格式全部保持不变**，前端无需任何修改。

### A.5 路由注册调整

`backend/app/routers/__init__.py`：将原 `ai_router` / `ai_config_router` 的导入改为从三个新文件导出对应 `router`。

`backend/app/main.py`：用新的三个路由替换原两个。

### A.6 向后兼容性

- 所有 URL 路径保持不变（仍为 `/api/v1/projects/{id}/ai/generate` 等）
- SSE 事件格式保持不变（`: connected`、`data: {...}`、`: heartbeat`、结束的 `data: {"done":true}` 等）
- 前端无需修改

---

## 方案 B：Prompt 模板外置

### B.1 目录结构

```
backend/app/prompts/
├── __init__.py              # 空文件，仅用于标识
├── continue.txt
├── rewrite.txt
├── expand.txt
├── outline.txt
├── character_analysis.txt
├── analyze_expand.txt
├── free_chat.txt
├── revise.txt
├── polish_character.txt
├── generate_title.txt
├── plot_enhance.txt
├── batch_outline.txt
├── batch_chapter.txt
├── wizard_outline_characters.txt
├── wizard_outline_only.txt
├── extract_characters.txt
└── remove_ai_traces.txt
```

**注意**：`prompts/` 目录已存在（`ls backend/app/` 显示），但未纳入本 prompt 体系。本轮会确认该目录用途后决定是直接使用还是另起新目录。**若已有内容冲突**，改用 `backend/app/prompt_templates/` 作为新目录。

### B.2 PromptManager 设计

文件：`backend/app/services/prompt_manager.py`

```python
"""Prompt 模板管理器。

启动时一次性从 prompts/ 目录加载所有 .txt 文件，运行期通过 format() 访问。
"""
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class PromptManager:
    """Prompt 模板管理器（单例风格的类方法接口）"""

    _templates: Dict[str, str] = {}
    _loaded: bool = False
    _prompts_dir: Path = Path(__file__).parent.parent / "prompts"

    @classmethod
    def load_all(cls) -> None:
        """从 prompts/ 目录加载所有 .txt 文件到内存。"""
        cls._templates.clear()
        if not cls._prompts_dir.exists():
            logger.error(f"Prompt 目录不存在：{cls._prompts_dir}")
            cls._loaded = True
            return

        for path in cls._prompts_dir.glob("*.txt"):
            try:
                content = path.read_text(encoding="utf-8")
                cls._templates[path.stem] = content
            except Exception as e:
                logger.error(f"加载 prompt 失败 {path}: {e}")

        cls._loaded = True
        logger.info(f"已加载 {len(cls._templates)} 个 prompt 模板")

    @classmethod
    def get(cls, name: str) -> str:
        """获取模板原文。"""
        if not cls._loaded:
            cls.load_all()
        if name not in cls._templates:
            raise KeyError(f"Prompt 模板不存在: {name}")
        return cls._templates[name]

    @classmethod
    def format(cls, name: str, **kwargs) -> str:
        """获取并填充模板。"""
        template = cls.get(name)
        return template.format(**kwargs)

    @classmethod
    def list_names(cls) -> list[str]:
        """列出所有已加载的模板名。"""
        if not cls._loaded:
            cls.load_all()
        return sorted(cls._templates.keys())
```

### B.3 启动时加载

`backend/app/main.py` 的 `lifespan`：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    PromptManager.load_all()  # 新增
    await init_db()
    yield
```

**关键决策：启动时一次性加载**，不做热重载。理由：
- 生产环境不需要热重载（开发者用户已记录"dev 阶段禁用所有缓存"的 feedback，但 prompt 变更本就是偶发的，Docker 重启成本低）
- 避免引入文件监听器依赖（`watchdog` 或手动轮询）
- 简化代码路径，减少出错可能

### B.4 ai_service.py 调用点迁移

**重构前：**
```python
from app.services.ai_service import PROMPTS

prompt = PROMPTS["continue"].format(content=content, context=context_text)
```

**重构后：**
```python
from app.services.prompt_manager import PromptManager

prompt = PromptManager.format("continue", content=content, context=context_text)
```

全局搜索 `PROMPTS[` 的所有引用点（预计在 `ai_service.py` 内部、`ai.py` / 新拆分路由、可能在 `script_ai_service.py` / `expansion_ai_service.py`）统一替换。

### B.5 Prompt 文件格式

每个 `.txt` 文件就是 prompt 的纯文本内容，占位符使用 Python `str.format()` 的 `{variable}` 语法。

**示例 `continue.txt`：**
```
你是一位经验丰富的小说作家。请根据以下已有内容，自然流畅地续写故事。
要求：
- 保持与原文一致的文风、语气和叙事节奏
- 续写内容应紧密衔接上文，情节合理推进
- 注意人物性格的一致性
- 续写约300-500字

{context}

已有内容：
{content}

请续写：
```

### B.6 兼容性与降级

- 若某个 prompt 文件缺失，`PromptManager.get()` 抛出 `KeyError` — 启动时如果某文件写错名字，会在首次调用时暴露，而不是启动时沉默失败
- `ai_service.py` 中保留 `PROMPTS` 模块级字典为空 dict 的空壳（标注 deprecated），避免第三方代码 `from app.services.ai_service import PROMPTS` 直接崩溃 — **决定：不保留兼容空壳**，直接删除，因为本项目不是库，没有外部依赖

---

## 方案 C：AiPanel 组件拆分

### C.1 当前 AiPanel.vue 职责分析

（基于已有的 1616 行结构）

| 职责模块 | 约行数 | 耦合度 |
|---------|-------|-------|
| 面板标题 + 历史/模板切换 | ~40 | 低 |
| 历史记录面板（展示、使用、清空） | ~150 | 低（独立 store） |
| 提示词模板面板（列表、分类、CRUD） | ~250 | 中 |
| 当前章节信息 | ~20 | 低 |
| AI 功能按钮组（续写/改写/扩写/分析/剧情完善等） | ~250 | 高（触发主流程） |
| SSE 流消费 + 生成中状态 | ~300 | 高（核心逻辑） |
| 输出结果展示 + 操作（插入/替换/重新生成） | ~200 | 中 |
| 上下文预览（实体列表 + 固定） | ~200 | 中 |
| 样式 | ~200 | - |

### C.2 拆分后结构

```
frontend/src/components/ai/
├── AiPanel.vue              # 主容器 ~150 行
│   职责：布局协调 + composable 调用 + 事件分发
├── AiHistoryPanel.vue       # ~150 行
│   职责：展示历史、选择项、清空（接收 history 列表，emit 事件）
├── AiTemplatePanel.vue      # ~200 行
│   职责：模板分类展示、使用、CRUD 对话框
├── AiActionBar.vue          # ~150 行
│   职责：AI 功能按钮集合，点击 emit action
├── AiOutputArea.vue         # ~200 行
│   职责：流式输出展示 + 插入/替换/重新生成 按钮
└── AiContextPreview.vue     # ~150 行
    职责：上下文实体列表展示、固定/取消固定
```

### C.3 Composable 抽取

文件：`frontend/src/composables/useAiGeneration.ts`（~200 行）

```ts
export function useAiGeneration(projectId: Ref<number>, chapterId: Ref<number | null>) {
  const generating = ref(false)
  const output = ref('')
  const error = ref<string | null>(null)
  const contextEntities = ref<ContextEntity[]>([])
  const abortController = ref<AbortController | null>(null)

  async function generate(params: GenerateParams) {
    // SSE fetch + EventSource 消费逻辑
    // 拼接 output.value
    // 捕获 context_used 事件 -> contextEntities
    // 捕获 error 事件 -> error
    // 完成时写入历史 store
  }

  function abort() {
    abortController.value?.abort()
    generating.value = false
  }

  return { generating, output, error, contextEntities, generate, abort }
}
```

### C.4 组件协作契约

**父 → 子（props）：**
- `AiHistoryPanel`: `history: HistoryItem[]`, `visible: boolean`
- `AiTemplatePanel`: `categorizedTemplates: Record<string, Template[]>`, `visible: boolean`
- `AiActionBar`: `disabled: boolean`（生成中禁用）, `chapterTitle?: string`
- `AiOutputArea`: `output: string`, `generating: boolean`, `canInsert: boolean`
- `AiContextPreview`: `entities: ContextEntity[]`, `pinnedIds: PinnedContext`

**子 → 父（emit）：**
- `AiHistoryPanel` → `use-item(item)`, `clear-all`
- `AiTemplatePanel` → `use-template(tpl)`, `create-template`, `edit-template(tpl)`, `delete-template(id)`
- `AiActionBar` → `action(actionType, options?)`
- `AiOutputArea` → `insert`, `replace`, `regenerate`
- `AiContextPreview` → `toggle-pin(entity)`

### C.5 AiPanel.vue 主容器草图

```vue
<template>
  <div class="ai-panel">
    <PanelHeader
      :provider="currentProvider"
      :show-history="showHistory"
      :show-templates="showTemplates"
      @toggle-history="showHistory = !showHistory"
      @toggle-templates="showTemplates = !showTemplates"
    />

    <AiHistoryPanel
      v-if="showHistory"
      :history="history"
      @use-item="useHistoryItem"
      @clear-all="clearHistory"
    />

    <AiTemplatePanel
      v-if="showTemplates"
      :categorized-templates="categorizedTemplates"
      @use-template="useTemplate"
      @create-template="openCreateDialog"
      @edit-template="openEditDialog"
      @delete-template="deleteTemplate"
    />

    <ChapterInfo :title="currentChapterTitle" />

    <AiActionBar
      :disabled="generating"
      :chapter-title="currentChapterTitle"
      @action="handleAction"
    />

    <AiContextPreview
      v-if="contextEntities.length > 0"
      :entities="contextEntities"
      :pinned-ids="pinnedContext"
      @toggle-pin="togglePin"
    />

    <AiOutputArea
      v-if="output || generating"
      :output="output"
      :generating="generating"
      :can-insert="canInsert"
      @insert="$emit('insert-text', output)"
      @replace="$emit('replace-text', output)"
      @regenerate="regenerate"
    />
  </div>
</template>

<script setup lang="ts">
const { generating, output, contextEntities, generate, abort } =
  useAiGeneration(projectId, chapterId)
// 事件处理 + 向父组件传递
</script>
```

### C.6 迁移策略

采用 **完全重写** 而非渐进拆分：
- 保留现有 `AiPanel.vue` 作为参考（Git 历史），新文件写在 `components/ai/` 下
- 所有 AiPanel.vue 的父组件只需要修改一行 import 路径
- 样式整体迁移到各子组件内（每个子组件内置自己的 scoped styles）

---

## 测试策略

### 后端（方案 A、B）

- **单元测试新增**：
  - `tests/test_sse_helper.py`：测试 SSEStreamHelper 的心跳、超时、异常处理
  - `tests/test_token_tracker.py`：测试 TokenTracker 的收集和 flush 逻辑
  - `tests/test_prompt_manager.py`：测试 PromptManager 加载、查找、格式化

- **集成测试**：对 `/api/v1/projects/{id}/ai/generate` 等端点做端到端 SSE 流测试（mock AIService）

- **手动验证**：
  - demo provider 下走通 continue/rewrite/expand/extract_characters/batch_generate 五条路径
  - 观察 SSE 流中 `: connected`、`: heartbeat`、`data: {...}` 的顺序与格式

### 前端（方案 C）

- **冒烟测试**：
  - 写作工作台正常生成 → 续写/改写/扩写按钮触发 → 结果正确展示 → 插入/替换生效
  - 历史记录面板点击历史项 → 内容正确填入
  - 模板面板：使用 / 创建 / 编辑 / 删除
  - 上下文预览：实体显示 / 固定 / 取消固定

---

## 回滚计划

每个方案为独立提交（commit），按方案粒度回滚：
- 方案 A 失败：`git revert <sse-commit-range>`
- 方案 B 失败：`git revert <prompt-commit>`
- 方案 C 失败：`git revert <aipanel-commit-range>`

方案 A 和 B 不共享代码（B 只在 ai_service.py 内部改动，A 在路由层改动），所以 B 的回滚不影响 A，反之亦然。

方案 C 完全独立于后端。

---

## 分阶段执行

| 阶段 | 方案 | 可独立合并？ |
|------|------|-------------|
| P1 | 方案 A — SSE 重构 | 是 |
| P2 | 方案 B — Prompt 外置 | 是（依赖 P1 已合并，但技术上独立） |
| P3 | 方案 C — AiPanel 拆分 | 是（与 P1/P2 完全独立，可并行） |

建议按 P1 → P2 → P3 的顺序合并主干。

---

## 成功标准

1. **代码行数收敛**：
   - `ai.py` 从 847 行拆为 3 个文件，每个 <300 行
   - `ai_service.py` 移除 PROMPTS 后减少 ~200 行
   - `AiPanel.vue` 从 1616 行拆为 6 个文件，每个 <250 行

2. **功能无回归**：
   - 所有 AI 端点 URL、请求/响应契约不变
   - 前端 Tiptap 编辑器 AI 调用行为完全一致
   - Token 使用记录的数据写入准确（demo 模式不记录，其他 provider 记录完整）

3. **新增代码可测试**：
   - SSEStreamHelper、TokenTracker、PromptManager 有单元测试覆盖
   - 测试总数从 16 增加到 ~25

---

## 风险与缓解

| 风险 | 等级 | 缓解 |
|------|------|------|
| SSE 重构导致心跳不稳定 / 客户端断连 | 中 | 保留 `": connected\n\n"` 初始探测、心跳间隔和最大心跳次数不变；demo provider 下做长时间运行测试 |
| Prompt 文件路径在 Docker 镜像中找不到 | 低 | 用 `Path(__file__).parent.parent / "prompts"` 绝对定位；CI 中加一个简单的启动时 assert |
| AiPanel 拆分后父组件事件断裂 | 低 | 保留原 AiPanel 导出，在新容器组件中通过 emit 向上完全透传 |
| 并发多人同时生成时 token 记录乱入 | 极低 | TokenTracker 是请求作用域实例，天然隔离（无全局可变状态） |

---

## 不做的事情（YAGNI）

- **不实现 prompt 热重载**：开发中 Docker 重启成本足够低
- **不实现 prompt 数据库化**：保持文件化，未来需要时再迁移到 DB
- **不做 AiPanel 的 Vuex/Pinia 状态提升**：composable 已足够隔离
- **不拆分 `ai_service.py` 本身**：本轮只移除 PROMPTS，service 类的进一步拆分留到后续轮次
- **不引入 Alembic 迁移工具**：这是另一个独立的大事项，应单独讨论
- **不改 drama 和 expansion 模块的 AI 服务**：它们有自己的 SSE 心跳实现，列为下一轮优化
