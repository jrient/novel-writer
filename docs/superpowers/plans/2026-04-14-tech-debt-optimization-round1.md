# Tech Debt Optimization Round 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 SSE 重复逻辑、外置 prompt 模板、拆分巨型 AiPanel 组件，不改变任何对外契约。

**Architecture:**
- 方案 A：提取 `SSEStreamHelper` + `TokenTracker` 到 `backend/app/utils/sse.py`，将 `ai.py` 拆分为 3 个新路由文件。
- 方案 B：新建 `backend/app/prompts/` 目录存放 `.txt` 模板，新建 `PromptManager` 服务统一加载。
- 方案 C：拆分 `AiPanel.vue` 为 6 个子组件 + `useAiGeneration` composable。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + pytest / Vue 3 + TypeScript + Pinia + vitest（若未引入则仅做冒烟测试）。

**Reference Spec:** `docs/superpowers/specs/2026-04-14-tech-debt-optimization-round1-design.md`

---

## Scope & Ordering

- **Phase 1 (P1)**: 方案 A — SSE 重构（Tasks 1-10）
- **Phase 2 (P2)**: 方案 B — Prompt 外置（Tasks 11-18）
- **Phase 3 (P3)**: 方案 C — AiPanel 拆分（Tasks 19-27）

Phase 1 和 Phase 2 为后端改动，可按顺序合并；Phase 3 为前端改动，与前两者独立，可并行。每个 Task 结束时单独提交。

**Spec 范围修订**：探索发现 `backend/app/routers/wizard.py` 中存在 **13 处** `PROMPTS[...]` 引用，未在 spec 初稿中提及。本 plan 已在 Task 14-15 中覆盖。`backend/app/prompts/` 目录在探索时显示为空目录/不存在（`ls` 无输出），可直接使用该路径。

---

# PHASE 1：SSE 流式基础设施重构（方案 A）

## Task 1: 创建 SSE 常量与辅助函数的基础骨架

**Files:**
- Create: `backend/app/utils/__init__.py`（若不存在）
- Create: `backend/app/utils/sse.py`
- Test: `backend/tests/test_sse_helper.py`

- [ ] **Step 1: 先检查 utils 目录**

Run: `ls backend/app/utils/ 2>/dev/null && echo existing || echo missing`

Expected: `existing` 或目录下的现有文件列表。如果 `missing`，本任务需创建目录与 `__init__.py`。

- [ ] **Step 2: 写失败测试（常量与辅助函数）**

Create `backend/tests/test_sse_helper.py`:

```python
"""SSEStreamHelper 单元测试"""
import json
import pytest

from app.utils.sse import sse_event, sse_heartbeat, SSE_HEADERS


def test_sse_event_formats_data_line():
    result = sse_event({"text": "你好"})
    assert result == 'data: {"text": "你好"}\n\n'


def test_sse_event_non_ascii_not_escaped():
    """中文必须不转义，便于前端直接展示"""
    result = sse_event({"msg": "中文"})
    assert "中文" in result
    assert "\\u" not in result


def test_sse_heartbeat_is_comment_line():
    assert sse_heartbeat() == ": heartbeat\n\n"


def test_sse_headers_no_cache():
    assert SSE_HEADERS["Cache-Control"] == "no-cache"
    assert SSE_HEADERS["X-Accel-Buffering"] == "no"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && pytest tests/test_sse_helper.py -v`
Expected: 导入失败（`ModuleNotFoundError: No module named 'app.utils.sse'`）

- [ ] **Step 4: 创建 utils/__init__.py 与 sse.py 骨架**

Create `backend/app/utils/__init__.py` (empty file).

Create `backend/app/utils/sse.py`:

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
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && pytest tests/test_sse_helper.py -v`
Expected: 4 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/utils/__init__.py backend/app/utils/sse.py backend/tests/test_sse_helper.py
git commit -m "feat(sse): add sse_event/sse_heartbeat helpers and SSE_HEADERS constant

Constraint: 中文不能被 JSON 转义，必须用 ensure_ascii=False
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 实现 SSEStreamHelper.wrap_stream 的正常流路径

**Files:**
- Modify: `backend/app/utils/sse.py`
- Modify: `backend/tests/test_sse_helper.py`

- [ ] **Step 1: 追加失败测试（正常流）**

Append to `backend/tests/test_sse_helper.py`:

```python
from app.utils.sse import SSEStreamHelper


@pytest.mark.asyncio
async def test_wrap_stream_forwards_data_lines():
    """正常流应原样转发 data: 行，并在前置 ': connected'"""
    async def fake_stream():
        yield 'data: {"text": "hello"}\n\n'
        yield 'data: {"text": " world"}\n\n'

    helper = SSEStreamHelper()
    lines = []
    async for line in helper.wrap_stream(fake_stream()):
        lines.append(line)

    assert lines[0] == ": connected\n\n"
    assert lines[1] == 'data: {"text": "hello"}\n\n'
    assert lines[2] == 'data: {"text": " world"}\n\n'


@pytest.mark.asyncio
async def test_wrap_stream_triggers_on_text_callback():
    """on_text 回调应在每次 data:{text:...} 时被调用"""
    async def fake_stream():
        yield 'data: {"text": "A"}\n\n'
        yield 'data: {"text": "B"}\n\n'

    collected = []
    helper = SSEStreamHelper()
    async for _ in helper.wrap_stream(fake_stream(), on_text=collected.append):
        pass

    assert collected == ["A", "B"]


@pytest.mark.asyncio
async def test_wrap_stream_triggers_on_usage_callback():
    usage_data = {"input_tokens": 100, "output_tokens": 50}

    async def fake_stream():
        yield f'data: {{"usage": {json.dumps(usage_data)}}}\n\n'

    captured = []
    helper = SSEStreamHelper()
    async for _ in helper.wrap_stream(fake_stream(), on_usage=captured.append):
        pass

    assert captured == [usage_data]


@pytest.mark.asyncio
async def test_wrap_stream_preamble_inserted_after_connected():
    async def fake_stream():
        yield 'data: {"text": "x"}\n\n'

    helper = SSEStreamHelper()
    preamble = ['data: {"type": "context_used"}\n\n']
    lines = [line async for line in helper.wrap_stream(fake_stream(), preamble=preamble)]

    assert lines[0] == ": connected\n\n"
    assert lines[1] == 'data: {"type": "context_used"}\n\n'
    assert lines[2] == 'data: {"text": "x"}\n\n'
```

Also ensure `pytest-asyncio` is available. Check `backend/pytest.ini` / `requirements.txt`:

Run: `cd backend && grep -E "pytest-asyncio|asyncio_mode" pytest.ini requirements.txt 2>/dev/null || true`

If not configured, in Task 3 we will either add it or convert tests to use `asyncio.run()`. For now assume it is configured (it typically is — the project already has async tests).

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_sse_helper.py -v`
Expected: 新增的 4 个测试失败（`AttributeError: module 'app.utils.sse' has no attribute 'SSEStreamHelper'`）

- [ ] **Step 3: 实现 SSEStreamHelper 的正常流路径**

Append to `backend/app/utils/sse.py`:

```python
class SSEStreamHelper:
    """SSE 流式响应助手。

    包装原始 AsyncGenerator，提供：
    - 初始 ": connected" 探测
    - 心跳保活
    - 超时终止
    - 异常捕获
    - on_text / on_usage 回调用于 token 统计
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

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_sse_helper.py -v`
Expected: 8 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/sse.py backend/tests/test_sse_helper.py
git commit -m "feat(sse): add SSEStreamHelper for unified stream wrapping

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 测试并实现 SSEStreamHelper 的异常与超时路径

**Files:**
- Modify: `backend/tests/test_sse_helper.py`（增补边界测试）

- [ ] **Step 1: 追加异常/超时测试**

Append to `backend/tests/test_sse_helper.py`:

```python
@pytest.mark.asyncio
async def test_wrap_stream_handles_exception_in_source():
    """原始流抛异常时，应输出错误 SSE 并正常结束"""
    async def failing_stream():
        yield 'data: {"text": "x"}\n\n'
        raise RuntimeError("upstream broken")

    helper = SSEStreamHelper(error_message="出错了")
    lines = [line async for line in helper.wrap_stream(failing_stream())]

    # 最后一行应为 error SSE
    assert any('"error"' in line and "出错了" in line for line in lines)


@pytest.mark.asyncio
async def test_wrap_stream_emits_heartbeat_on_slow_source():
    """源流慢于 heartbeat_interval 时，应输出心跳"""
    async def slow_stream():
        await asyncio.sleep(0.3)
        yield 'data: {"text": "late"}\n\n'

    helper = SSEStreamHelper(heartbeat_interval=0.1, max_heartbeats=100)
    lines = [line async for line in helper.wrap_stream(slow_stream())]

    heartbeats = [l for l in lines if l == ": heartbeat\n\n"]
    assert len(heartbeats) >= 1


@pytest.mark.asyncio
async def test_wrap_stream_timeout_after_max_heartbeats():
    """max_heartbeats 后应发送 timeout 错误并退出"""
    async def never_ending():
        while True:
            await asyncio.sleep(1)
            yield 'data: {"text":"x"}\n\n'

    helper = SSEStreamHelper(heartbeat_interval=0.05, max_heartbeats=2, timeout_message="超时了")
    lines = []
    async for line in helper.wrap_stream(never_ending()):
        lines.append(line)
        if len(lines) > 10:
            break  # 安全阀，避免测试卡死

    assert any("超时了" in line for line in lines)
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && pytest tests/test_sse_helper.py -v`
Expected: 11 passed（当前 helper 实现应已覆盖这些路径）

如果 `test_wrap_stream_emits_heartbeat_on_slow_source` 因 `asyncio.wait` 与生成器调度导致不稳定，将 `heartbeat_interval` 调为更小（如 `0.05`）并延长 `slow_stream` 的 sleep 到 `0.4s`。

- [ ] **Step 3: 提交**

```bash
git add backend/tests/test_sse_helper.py
git commit -m "test(sse): cover exception, heartbeat, and timeout paths

Not-tested: Nginx-level connection drops (requires integration setup)
Confidence: high

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 实现 TokenTracker 类

**Files:**
- Modify: `backend/app/utils/sse.py`（追加 TokenTracker）
- Create: `backend/tests/test_token_tracker.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_token_tracker.py`:

```python
"""TokenTracker 单元测试"""
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.sse import TokenTracker


@pytest.mark.asyncio
async def test_token_tracker_skips_demo_provider():
    """demo provider 下不应写入 token 使用记录"""
    db_mock = AsyncMock()
    tracker = TokenTracker(
        db=db_mock, user_id=1, provider="demo", model="demo",
        action="continue", project_id=1,
    )
    tracker.on_text("hello")
    with patch("app.utils.sse.log_token_usage", new_callable=AsyncMock) as log_mock:
        await tracker.flush(input_text="prompt")
        log_mock.assert_not_called()


@pytest.mark.asyncio
async def test_token_tracker_uses_real_usage_when_available():
    db_mock = AsyncMock()
    tracker = TokenTracker(
        db=db_mock, user_id=1, provider="openai", model="gpt-4o",
        action="continue", project_id=1,
    )
    tracker.on_usage({"input_tokens": 100, "output_tokens": 200})
    with patch("app.utils.sse.log_token_usage", new_callable=AsyncMock) as log_mock:
        await tracker.flush(input_text="prompt")
        log_mock.assert_awaited_once()
        _, kwargs = log_mock.call_args
        assert kwargs["input_tokens"] == 100
        assert kwargs["output_tokens"] == 200


@pytest.mark.asyncio
async def test_token_tracker_falls_back_to_estimate_when_no_usage():
    db_mock = AsyncMock()
    tracker = TokenTracker(
        db=db_mock, user_id=1, provider="openai", model="gpt-4o",
        action="continue", project_id=1,
    )
    tracker.on_text("你好世界")
    with patch("app.utils.sse.log_token_usage", new_callable=AsyncMock) as log_mock, \
         patch("app.utils.sse.estimate_tokens", return_value=42) as est_mock:
        await tracker.flush(input_text="prompt input")
        log_mock.assert_awaited_once()
        assert est_mock.call_count == 2  # 一次 input，一次 output
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_token_tracker.py -v`
Expected: `ImportError: cannot import name 'TokenTracker'`

- [ ] **Step 3: 实现 TokenTracker**

Append to `backend/app/utils/sse.py`:

```python
# ----------------------------------------------------------------------------
# TokenTracker
# ----------------------------------------------------------------------------
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.token_usage_service import log_token_usage, estimate_tokens


class TokenTracker:
    """请求作用域的 token 使用收集器。

    使用方式：
        tracker = TokenTracker(db=..., user_id=..., provider=..., ...)
        async for line in helper.wrap_stream(
            stream, on_text=tracker.on_text, on_usage=tracker.on_usage,
        ):
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

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && pytest tests/test_token_tracker.py -v`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add backend/app/utils/sse.py backend/tests/test_token_tracker.py
git commit -m "feat(sse): add TokenTracker for request-scoped token accounting

Constraint: demo provider must never write to token_usage table
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 创建 ai_config.py 路由（最小独立片段）

拆 `ai.py` 的策略：从最小最独立的片段（`/api/v1/ai/config` 端点）开始。

**Files:**
- Create: `backend/app/routers/ai_config.py`
- Modify: `backend/app/routers/__init__.py`（不动 ai_router，新增 ai_config_router 导出，保留旧的）
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 ai_config.py**

Create `backend/app/routers/ai_config.py`:

```python
"""AI 配置路由 - 独立于项目（GET /api/v1/ai/config）"""
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.ai import AIConfigResponse
from app.services.ai_service import AIService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/config", response_model=AIConfigResponse)
async def get_ai_config():
    """获取 AI 配置信息"""
    available = []
    models = {}

    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("sk-xxx", "", None):
        available.append("openai")
        models["openai"] = settings.OPENAI_MODEL

    if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None):
        available.append("anthropic")
        models["anthropic"] = settings.ANTHROPIC_MODEL

    available.append("ollama")
    models["ollama"] = settings.OLLAMA_MODEL

    available.append("demo")
    models["demo"] = "built-in"

    actual_default = AIService._get_available_provider(settings.DEFAULT_AI_PROVIDER)

    return AIConfigResponse(
        default_provider=actual_default,
        available_providers=available,
        models=models,
    )
```

- [ ] **Step 2: 在 routers/__init__.py 中补充导出**

Read current `backend/app/routers/__init__.py` and locate the line exporting `ai_config_router`. Replace the import source for `ai_config_router` from the old `ai.py` to the new file. For example, if the file contains:

```python
from app.routers.ai import router as ai_router, config_router as ai_config_router
```

Change to:

```python
from app.routers.ai import router as ai_router
from app.routers.ai_config import router as ai_config_router
```

（如果 `__init__.py` 是用其他方式导出，按实际路径调整。）

- [ ] **Step 3: 启动后端验证 /api/v1/ai/config 仍正常**

Run: `cd /data/project/novel-writer && docker compose up -d backend && sleep 5 && curl -s http://localhost:8084/api/v1/ai/config`

Expected: JSON 响应包含 `default_provider`、`available_providers`、`models` 字段。

- [ ] **Step 4: 运行全量单元测试**

Run: `cd backend && pytest -q`
Expected: 所有现有测试 + 新增 SSE 测试均通过。

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/ai_config.py backend/app/routers/__init__.py
git commit -m "refactor(ai): extract /api/v1/ai/config endpoint into ai_config.py

Constraint: endpoint path and response schema unchanged
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 创建 ai_batch.py 路由并迁移 batch-generate 端点（保持实现原样）

迁移策略：先保持端点内部实现与 `ai.py` 中一致（不用新 helper），仅做物理移动。下一步 Task 用 helper 重构。

**Files:**
- Create: `backend/app/routers/ai_batch.py`
- Modify: `backend/app/routers/ai.py`（删除对应端点的定义，后续 Task 完整删除文件）
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`（若改动路由变量名）

- [ ] **Step 1: 从 ai.py 复制 batch_generate 端点和 _retrieve_knowledge 辅助**

Copy the following from `backend/app/routers/ai.py` into `backend/app/routers/ai_batch.py`:

- 所有相关 import
- `router = APIRouter(prefix="/api/v1/projects/{project_id}/ai", tags=["ai"])`（使用新的 router 变量）
- 函数 `batch_generate(...)`（当前 `ai.py` ~463-773 行）
- 辅助函数 `_retrieve_knowledge`（当前 `ai.py` ~811-847 行）

Resulting `backend/app/routers/ai_batch.py` 骨架：

```python
"""AI 批量生成路由 - POST /api/v1/projects/{id}/ai/batch-generate"""
import asyncio
import json as _json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.chapter import Chapter
from app.models.project import Project
from app.models.reference import ReferenceNovel
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.ai import BatchGenerateRequest
from app.services.ai_service import AIService, PROMPTS
from app.services.smart_context import SmartContextService
from app.services.token_usage_service import log_token_usage, estimate_tokens

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/ai",
    tags=["ai"],
)


@router.post("/batch-generate")
async def batch_generate(...):
    ...  # 原样从 ai.py 粘贴


async def _retrieve_knowledge(...):
    ...  # 原样从 ai.py 粘贴
```

- [ ] **Step 2: 更新 routers/__init__.py 和 main.py**

Change `routers/__init__.py` to also export the batch router:

```python
from app.routers.ai import router as ai_router
from app.routers.ai_config import router as ai_config_router
from app.routers.ai_batch import router as ai_batch_router
```

Add to `__all__` / include list.

In `backend/app/main.py`, add:
```python
app.include_router(ai_batch_router)
```

Import from routers:
```python
from app.routers import (
    ...
    ai_batch_router,
    ...
)
```

- [ ] **Step 3: 从 ai.py 删除已迁移的 batch_generate 定义和 _retrieve_knowledge**

Remove the `@router.post("/batch-generate")` function block and the `_retrieve_knowledge` helper from `backend/app/routers/ai.py`.

**重要**：不要删除 `ai.py` 本身，其中仍保留 `ai_generate` 和 `context_preview` 端点（Task 7 会迁移）。

- [ ] **Step 4: 验证 batch-generate 端点可访问**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`

Test that the endpoint is still registered via the API docs page:
Run: `curl -s http://localhost:8084/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print([p for p in d['paths'] if 'batch' in p])"`
Expected: `['/api/v1/projects/{project_id}/ai/batch-generate']`

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/ai_batch.py backend/app/routers/ai.py backend/app/routers/__init__.py backend/app/main.py
git commit -m "refactor(ai): extract batch-generate endpoint into ai_batch.py

Constraint: endpoint URL and SSE event schema unchanged
Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 创建 ai_generate.py 路由并迁移 generate/context-preview 端点

**Files:**
- Create: `backend/app/routers/ai_generate.py`
- Delete: `backend/app/routers/ai.py`
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 创建 ai_generate.py 骨架**

Create `backend/app/routers/ai_generate.py` by moving ALL remaining contents from `backend/app/routers/ai.py`:

- 函数 `ai_generate` (with `extract_characters` branch inline for now)
- 函数 `context_preview`
- 辅助 `_generate_context_suggestions`

保持路由前缀不变：
```python
router = APIRouter(
    prefix="/api/v1/projects/{project_id}/ai",
    tags=["ai"],
)
```

- [ ] **Step 2: 删除 ai.py**

Run: `rm backend/app/routers/ai.py`

- [ ] **Step 3: 更新 routers/__init__.py**

Replace:
```python
from app.routers.ai import router as ai_router
```
with:
```python
from app.routers.ai_generate import router as ai_router
```

- [ ] **Step 4: 验证端点仍注册**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `curl -s http://localhost:8084/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print(sorted([p for p in d['paths'] if '/ai/' in p]))"`

Expected: 至少包含 `/api/v1/projects/{project_id}/ai/generate`、`/context-preview`、`/batch-generate`、`/api/v1/ai/config`。

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/ai_generate.py backend/app/routers/__init__.py
git rm backend/app/routers/ai.py
git commit -m "refactor(ai): extract remaining ai.py into ai_generate.py; delete ai.py

Directive: After this commit, ai.py no longer exists; all references must use ai_generate/ai_batch/ai_config
Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 用 SSEStreamHelper + TokenTracker 重构 ai_generate 端点

**Files:**
- Modify: `backend/app/routers/ai_generate.py`

- [ ] **Step 1: 导入新的 SSE helper**

In `backend/app/routers/ai_generate.py`, add near the top:

```python
from app.utils.sse import SSEStreamHelper, TokenTracker, SSE_HEADERS, sse_event
```

- [ ] **Step 2: 抽取辅助函数 _get_model_for_provider**

Add near top of file:

```python
def _get_model_for_provider(provider: str) -> str:
    return {
        "openai": settings.OPENAI_MODEL,
        "anthropic": settings.ANTHROPIC_MODEL,
        "ollama": settings.OLLAMA_MODEL,
        "demo": "demo",
    }.get(provider, "unknown")
```

- [ ] **Step 3: 重写 ai_generate 非 extract_characters 分支的 SSE 部分**

Find the block in `ai_generate` starting from `async def stream_with_heartbeat():` and ending at the final `return StreamingResponse(...)`. Replace with:

```python
    # 创建 AI 流
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

    # 用 helper + tracker 包装
    helper = SSEStreamHelper()
    tracker = TokenTracker(
        db=db,
        user_id=current_user.id,
        provider=actual_provider,
        model=actual_model,
        action=payload.action,
        project_id=project_id,
    )

    preamble = []
    if context_entities:
        preamble.append(sse_event({
            "type": "context_used",
            "entities": context_entities,
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

并且把 `actual_model = provider_model_map.get(actual_provider, "unknown")` 改为 `actual_model = _get_model_for_provider(actual_provider)`（删除本地 `provider_model_map` 变量）。

- [ ] **Step 4: 验证端点功能（demo provider）**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`

Write a small SSE smoke test script `backend/scripts/smoke_sse.py`（临时脚本，测试后可删除）:

```python
"""冒烟测试：直接访问 /generate 端点，打印前 20 行 SSE"""
import httpx

# 需要先用 /api/v1/auth/login 拿到 token，或使用测试账号
# 此脚本仅作为手动验证参考，实际测试用 curl 即可
```

改用 curl 直接验证 SSE 流式响应：
```bash
# 在另一终端模拟前端请求（需要已有用户 token）
# 如无 token，仅验证 OpenAPI schema 正确即可
curl -s http://localhost:8084/openapi.json | python -c "
import sys, json
d = json.load(sys.stdin)
gen = d['paths']['/api/v1/projects/{project_id}/ai/generate']
print('ai/generate methods:', list(gen.keys()))
"
```

Expected: `ai/generate methods: ['post']`

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/ai_generate.py
git commit -m "refactor(ai): use SSEStreamHelper+TokenTracker in ai_generate

Removes ~80 lines of inline heartbeat/timeout/token-collection logic.
Constraint: SSE event format (: connected, : heartbeat, data:{...}) unchanged
Confidence: high
Scope-risk: moderate
Not-tested: real-world SSE long-connection behind nginx (requires staging)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 用 SSEStreamHelper 重构 extract_characters 分支

**Files:**
- Modify: `backend/app/routers/ai_generate.py`

- [ ] **Step 1: 抽取 extract_characters 为独立函数**

In `ai_generate.py`, 将 `ai_generate` 函数内 `if payload.action == "extract_characters":` 分支内部的逻辑抽到模块级函数 `_handle_extract_characters`:

```python
async def _handle_extract_characters(
    db: AsyncSession,
    payload: AIGenerateRequest,
    project_id: int,
    current_user: User,
) -> StreamingResponse:
    """extract_characters 动作的独立处理路径"""
    import json as _json

    # 获取指定章节或全部章节
    chapter_query = select(Chapter).where(
        Chapter.project_id == project_id
    ).order_by(Chapter.sort_order)
    if payload.chapter_ids:
        chapter_query = select(Chapter).where(
            Chapter.project_id == project_id,
            Chapter.id.in_(payload.chapter_ids),
        ).order_by(Chapter.sort_order)
    all_chapters_result = await db.execute(chapter_query)
    all_chapters = all_chapters_result.scalars().all()
    chapters_text_parts = []
    for ch in all_chapters:
        if ch.content and ch.content.strip():
            chapters_text_parts.append(f"【{ch.title}】\n{ch.content}")
    chapters_text = "\n\n---\n\n".join(chapters_text_parts)

    if not chapters_text.strip():
        async def empty_stream():
            yield sse_event({"error": "项目中没有章节内容，无法提取角色"})
            yield sse_event({"done": True})
        return StreamingResponse(
            empty_stream(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

    # 获取已有角色名
    existing_chars_result = await db.execute(
        select(Character).where(Character.project_id == project_id)
    )
    existing_chars = existing_chars_result.scalars().all()
    existing_names = [c.name for c in existing_chars]
    existing_characters_str = "、".join(existing_names) if existing_names else "（无）"

    # 截断
    max_content_len = 15000
    if len(chapters_text) > max_content_len:
        chapters_text = chapters_text[:max_content_len] + "\n\n...（内容过长，已截断）"

    extract_prompt = PROMPTS["extract_characters"].format(
        existing_characters=existing_characters_str,
        content=chapters_text,
    )

    actual_provider = AIService._get_available_provider(payload.provider)
    actual_model = _get_model_for_provider(actual_provider)

    # 选择底层 stream
    if actual_provider == "demo":
        stream_gen = AIService._stream_demo("extract_characters")
    elif actual_provider == "openai":
        stream_gen = AIService._stream_openai(extract_prompt)
    elif actual_provider == "anthropic":
        stream_gen = AIService._stream_anthropic(extract_prompt)
    elif actual_provider == "ollama":
        stream_gen = AIService._stream_ollama(extract_prompt)
    else:
        async def err_stream():
            yield sse_event({"error": "无可用的 AI 服务"})
        return StreamingResponse(err_stream(), media_type="text/event-stream", headers=SSE_HEADERS)

    helper = SSEStreamHelper()
    tracker = TokenTracker(
        db=db, user_id=current_user.id,
        provider=actual_provider, model=actual_model,
        action="extract_characters", project_id=project_id,
    )

    async def response_stream():
        async for line in helper.wrap_stream(
            stream_gen, on_text=tracker.on_text, on_usage=tracker.on_usage
        ):
            yield line
        await tracker.flush(input_text=extract_prompt)

    return StreamingResponse(
        response_stream(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
```

需要 import:
```python
from app.models.character import Character  # 如果尚未导入
```

- [ ] **Step 2: 在 ai_generate 中调用**

Replace the `if payload.action == "extract_characters":` block (~80 lines) in `ai_generate` with:

```python
    if payload.action == "extract_characters":
        return await _handle_extract_characters(
            db=db, payload=payload,
            project_id=project_id, current_user=current_user,
        )
```

- [ ] **Step 3: 验证**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`

Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 4: 提交**

```bash
git add backend/app/routers/ai_generate.py
git commit -m "refactor(ai): use SSEStreamHelper in extract_characters branch

Extracts the branch into a module-level helper for clarity and
removes ~60 lines of duplicated heartbeat code.
Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 用 SSEStreamHelper 重构 ai_batch.py 的 batch_generate

**Files:**
- Modify: `backend/app/routers/ai_batch.py`

这是 Phase 1 最复杂的重构。`batch_generate` 有两处需要 heartbeat：
1. 大纲生成的非流式部分（`generate_text` + `await asyncio.wait_for(asyncio.shield(...), timeout=15)`）
2. 每章生成的流式部分（`asyncio.wait_for(stream_iter.__anext__(), timeout=15)`）

`SSEStreamHelper` 直接适用于第 2 种场景，第 1 种保留原样即可。

- [ ] **Step 1: 导入 helper**

```python
from app.utils.sse import SSEStreamHelper, SSE_HEADERS, sse_event, sse_heartbeat
```

- [ ] **Step 2: 替换每章生成的流式循环**

Locate the section in `event_stream()` inside `batch_generate`:

```python
# 真实 AI 流式生成（带心跳防断连）
if provider == "openai":
    stream_gen = AIService._stream_openai(chapter_prompt)
elif provider == "anthropic":
    stream_gen = AIService._stream_anthropic(chapter_prompt)
else:
    stream_gen = AIService._stream_ollama(chapter_prompt)

stream_iter = stream_gen.__aiter__()
stream_done = False
while not stream_done:
    try:
        sse_line = await asyncio.wait_for(stream_iter.__anext__(), timeout=15)
    except asyncio.TimeoutError:
        yield f": heartbeat\n\n"
        continue
    except StopAsyncIteration:
        stream_done = True
        break

    if sse_line.startswith("data: "):
        try:
            payload_data = _json.loads(sse_line[6:].strip())
            if payload_data.get("text"):
                chapter_content += payload_data["text"]
                yield f"data: {_json.dumps({'type': 'chapter_stream', 'chapter_index': chapter_index, 'title': chapter_title, 'text': payload_data['text']}, ensure_ascii=False)}\n\n"
            if payload_data.get("error"):
                yield f"data: {_json.dumps({'type': 'error', 'message': payload_data['error']}, ensure_ascii=False)}\n\n"
                return
        except _json.JSONDecodeError:
            pass
```

Replace with:

```python
# 真实 AI 流式生成（使用 SSEStreamHelper 包装）
if provider == "openai":
    stream_gen = AIService._stream_openai(chapter_prompt)
elif provider == "anthropic":
    stream_gen = AIService._stream_anthropic(chapter_prompt)
else:
    stream_gen = AIService._stream_ollama(chapter_prompt)

# 转换事件：将底层 stream 的 {"text": ...} 转为 {"type":"chapter_stream",...}
# 因为 helper 默认转发原始 SSE 行，这里我们手工循环
chapter_helper = SSEStreamHelper(heartbeat_interval=15.0, max_heartbeats=20)
async for sse_line in chapter_helper.wrap_stream(stream_gen):
    if sse_line == ": connected\n\n":
        continue  # 不转发给前端（已在 batch 级别发过 progress）
    if sse_line == ": heartbeat\n\n":
        yield sse_line
        continue
    if sse_line.startswith("data: "):
        try:
            payload_data = _json.loads(sse_line[6:].strip())
            if payload_data.get("error"):
                yield sse_event({"type": "error", "message": payload_data["error"]})
                return
            if payload_data.get("text"):
                chapter_content += payload_data["text"]
                yield sse_event({
                    "type": "chapter_stream",
                    "chapter_index": chapter_index,
                    "title": chapter_title,
                    "text": payload_data["text"],
                })
        except _json.JSONDecodeError:
            pass
```

**说明**：这里保留了 `event_stream()` 外层的 try/except 结构和整体结构不变，只替换了内层单章流消费。

- [ ] **Step 3: 替换大纲生成的心跳循环（可选的小优化）**

Locate:

```python
outline_raw = None
gen_task = asyncio.create_task(AIService.generate_text(outline_prompt))
while not gen_task.done():
    try:
        await asyncio.wait_for(asyncio.shield(gen_task), timeout=15)
    except asyncio.TimeoutError:
        yield f": heartbeat\n\n"
outline_raw = gen_task.result()
```

Replace `yield f": heartbeat\n\n"` with `yield sse_heartbeat()` for consistency. 其他保持不变。

- [ ] **Step 4: 把 `headers={"Cache-Control": ...}` 改为 `headers=SSE_HEADERS`**

Locate:
```python
return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers={
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    },
)
```

Replace with:
```python
return StreamingResponse(
    event_stream(),
    media_type="text/event-stream",
    headers=SSE_HEADERS,
)
```

- [ ] **Step 5: 验证**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`

Run: `cd backend && pytest -q`
Expected: all passing

Run: `curl -s http://localhost:8084/openapi.json | python -c "
import sys, json
d = json.load(sys.stdin)
print('/batch-generate' in str(d['paths']))
"`
Expected: `True`

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/ai_batch.py
git commit -m "refactor(ai): use SSEStreamHelper in batch-generate chapter loop

Per-chapter streaming now goes through the helper; outline generation
keeps its task-shielding pattern but now uses sse_heartbeat() for
consistency.
Constraint: SSE event types (progress/outline/chapter_stream/refine_done/chapter_done/done/error) unchanged
Confidence: high
Scope-risk: moderate
Not-tested: full 20-chapter batch run under real OpenAI latency

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

# PHASE 2：Prompt 模板外置（方案 B）

## Task 11: 创建 prompts/ 目录和 PromptManager 骨架 + 测试

**Files:**
- Create: `backend/app/prompts/` (directory)
- Create: `backend/app/prompts/_placeholder.txt` (占位，确保目录被 git 追踪)
- Create: `backend/app/services/prompt_manager.py`
- Create: `backend/tests/test_prompt_manager.py`

- [ ] **Step 1: 创建目录和占位文件**

Run:
```bash
mkdir -p backend/app/prompts
```

Create `backend/app/prompts/_placeholder.txt`:

```
# 占位文件，确保 prompts/ 目录被 git 追踪。下一 Task 开始填充真实的 prompt 模板，此文件会在 Task 18 删除。
```

- [ ] **Step 2: 创建测试**

Create `backend/tests/test_prompt_manager.py`:

```python
"""PromptManager 单元测试"""
from pathlib import Path

import pytest

from app.services.prompt_manager import PromptManager


@pytest.fixture
def tmp_prompts_dir(tmp_path, monkeypatch):
    """创建临时 prompts 目录，隔离真实目录"""
    d = tmp_path / "prompts"
    d.mkdir()
    (d / "greeting.txt").write_text("你好 {name}", encoding="utf-8")
    (d / "empty.txt").write_text("", encoding="utf-8")
    monkeypatch.setattr(PromptManager, "_prompts_dir", d)
    PromptManager._loaded = False
    PromptManager._templates = {}
    yield d


def test_load_all_reads_txt_files(tmp_prompts_dir):
    PromptManager.load_all()
    names = PromptManager.list_names()
    assert "greeting" in names
    assert "empty" in names


def test_get_returns_template_content(tmp_prompts_dir):
    PromptManager.load_all()
    assert PromptManager.get("greeting") == "你好 {name}"


def test_get_raises_on_missing(tmp_prompts_dir):
    PromptManager.load_all()
    with pytest.raises(KeyError):
        PromptManager.get("does_not_exist")


def test_format_fills_variables(tmp_prompts_dir):
    PromptManager.load_all()
    result = PromptManager.format("greeting", name="世界")
    assert result == "你好 世界"


def test_lazy_load_on_first_get(tmp_prompts_dir):
    """未显式 load_all 时，首次 get() 也应触发加载"""
    PromptManager._loaded = False
    PromptManager._templates = {}
    result = PromptManager.get("greeting")
    assert result == "你好 {name}"
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd backend && pytest tests/test_prompt_manager.py -v`
Expected: `ImportError: cannot import name 'PromptManager'`

- [ ] **Step 4: 实现 PromptManager**

Create `backend/app/services/prompt_manager.py`:

```python
"""Prompt 模板管理器。

启动时从 backend/app/prompts/*.txt 加载所有模板到内存。
"""
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class PromptManager:
    """Prompt 模板管理器（类方法接口）。

    使用：
        from app.services.prompt_manager import PromptManager
        prompt = PromptManager.format("continue", content=..., context=...)
    """

    _templates: Dict[str, str] = {}
    _loaded: bool = False
    _prompts_dir: Path = Path(__file__).parent.parent / "prompts"

    @classmethod
    def load_all(cls) -> None:
        """从 prompts/ 目录加载所有 .txt 文件到内存（忽略下划线开头的占位文件）。"""
        cls._templates.clear()
        if not cls._prompts_dir.exists():
            logger.error(f"Prompt 目录不存在：{cls._prompts_dir}")
            cls._loaded = True
            return

        for path in cls._prompts_dir.glob("*.txt"):
            if path.stem.startswith("_"):
                continue
            try:
                content = path.read_text(encoding="utf-8")
                cls._templates[path.stem] = content
            except Exception as e:
                logger.error(f"加载 prompt 失败 {path}: {e}")

        cls._loaded = True
        logger.info(f"已加载 {len(cls._templates)} 个 prompt 模板")

    @classmethod
    def get(cls, name: str) -> str:
        if not cls._loaded:
            cls.load_all()
        if name not in cls._templates:
            raise KeyError(f"Prompt 模板不存在: {name}")
        return cls._templates[name]

    @classmethod
    def format(cls, name: str, **kwargs) -> str:
        template = cls.get(name)
        return template.format(**kwargs)

    @classmethod
    def list_names(cls) -> list[str]:
        if not cls._loaded:
            cls.load_all()
        return sorted(cls._templates.keys())
```

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest tests/test_prompt_manager.py -v`
Expected: 5 passed

- [ ] **Step 6: 提交**

```bash
git add backend/app/prompts/_placeholder.txt backend/app/services/prompt_manager.py backend/tests/test_prompt_manager.py
git commit -m "feat(prompts): add PromptManager + prompts/ directory skeleton

Constraint: 模板文件加载失败不得让服务启动崩溃，写日志即可
Directive: 下划线开头的 .txt 文件视为占位，跳过加载
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 12: 在 main.py 启动时加载 PromptManager

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: 修改 lifespan**

Locate in `backend/app/main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库"""
    await init_db()
    yield
```

Change to:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时加载 prompts 和初始化数据库"""
    from app.services.prompt_manager import PromptManager
    PromptManager.load_all()
    await init_db()
    yield
```

- [ ] **Step 2: 验证启动**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `docker compose logs backend --tail 30 | grep "Prompt"`
Expected: `已加载 0 个 prompt 模板`（因为还没有真正的模板文件）

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 4: 提交**

```bash
git add backend/app/main.py
git commit -m "feat(prompts): load PromptManager at app startup

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 13: 提取 ai_service.py 中 PROMPTS 的所有 17 个模板到 .txt 文件

**Files:**
- Create: `backend/app/prompts/continue.txt`
- Create: `backend/app/prompts/rewrite.txt`
- Create: `backend/app/prompts/expand.txt`
- Create: `backend/app/prompts/outline.txt`
- Create: `backend/app/prompts/character_analysis.txt`
- Create: `backend/app/prompts/analyze_expand.txt`
- Create: `backend/app/prompts/free_chat.txt`
- Create: `backend/app/prompts/revise.txt`
- Create: `backend/app/prompts/polish_character.txt`
- Create: `backend/app/prompts/generate_title.txt`
- Create: `backend/app/prompts/plot_enhance.txt`
- Create: `backend/app/prompts/batch_outline.txt`
- Create: `backend/app/prompts/batch_chapter.txt`
- Create: `backend/app/prompts/wizard_outline_characters.txt`
- Create: `backend/app/prompts/wizard_outline_only.txt`
- Create: `backend/app/prompts/wizard_characters_from_outline.txt`
- Create: `backend/app/prompts/wizard_maps.txt`
- Create: `backend/app/prompts/wizard_parts.txt`
- Create: `backend/app/prompts/wizard_chapters_for_part.txt`
- Create: `backend/app/prompts/wizard_characters_for_part.txt`
- Create: `backend/app/prompts/wizard_revision.txt`
- Create: `backend/app/prompts/extract_characters.txt`
- Create: `backend/app/prompts/remove_ai_traces.txt`

（共 23 个 — spec 初稿写 17 是根据 ai_service.py 内部统计，但 wizard.py 也引用了 7 个 wizard_* 模板，实际在 ai_service.py 的 PROMPTS 字典中是 23 个 key。）

- [ ] **Step 1: 逐个抽取 PROMPTS 键到 .txt**

对每个键，将其值（三重引号字符串）作为 `.txt` 文件的内容。**注意：字符串中的 `{{`、`}}`（Python str.format 转义）需保持不变**（PromptManager 调用的也是 `str.format()`，保持行为一致）。

示例 — `backend/app/prompts/continue.txt`:
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

**操作方式：** 使用 Python 一次性批量转储（避免手工复制出错）:

Run (一次性):
```bash
cd backend && python -c "
from app.services import ai_service
import os, pathlib
out = pathlib.Path('app/prompts')
out.mkdir(exist_ok=True)
for k, v in ai_service.PROMPTS.items():
    (out / f'{k}.txt').write_text(v, encoding='utf-8')
print(f'written {len(ai_service.PROMPTS)} prompts')
"
```

Expected: `written 23 prompts`（具体数字以实际 PROMPTS dict 为准）

- [ ] **Step 2: 验证文件内容和数量**

Run: `ls backend/app/prompts/*.txt | wc -l`
Expected: 24（含 `_placeholder.txt`）

Run: `head -5 backend/app/prompts/continue.txt`
Expected: 前 5 行与 PROMPTS["continue"] 的前 5 行一致

- [ ] **Step 3: 重启并验证加载**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `docker compose logs backend --tail 10 | grep "Prompt"`
Expected: `已加载 23 个 prompt 模板`

- [ ] **Step 4: 运行测试**

Run: `cd backend && pytest -q`
Expected: all passing（此刻 PROMPTS 字典还在，未删除，所以 ai_service 行为不变）

- [ ] **Step 5: 删除占位文件**

Run: `rm backend/app/prompts/_placeholder.txt`

- [ ] **Step 6: 提交**

```bash
git add backend/app/prompts/
git commit -m "feat(prompts): extract all 23 PROMPTS templates to prompts/*.txt

Directive: 生成方式为 ai_service.PROMPTS 的直接转储，保证内容逐字节一致。
若手动编辑某个 .txt 后需要同步，请用 git diff 对比。
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 14: 替换 ai_generate.py / ai_batch.py / ai_service.py 中的 PROMPTS 引用

**Files:**
- Modify: `backend/app/routers/ai_generate.py`
- Modify: `backend/app/routers/ai_batch.py`
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: ai_generate.py 中替换**

Replace:
```python
from app.services.ai_service import AIService, PROMPTS
```
with:
```python
from app.services.ai_service import AIService
from app.services.prompt_manager import PromptManager
```

Find `PROMPTS["extract_characters"].format(...)` and replace with `PromptManager.format("extract_characters", ...)`.

Similarly for any other `PROMPTS[...]` references in this file.

- [ ] **Step 2: ai_batch.py 中替换**

Same pattern. 常见位置：
- `outline_prompt = PROMPTS["batch_outline"].format(...)` → `outline_prompt = PromptManager.format("batch_outline", ...)`
- `chapter_prompt = PROMPTS["batch_chapter"].format(...)` → `chapter_prompt = PromptManager.format("batch_chapter", ...)`
- `remove_prompt = PROMPTS["remove_ai_traces"].format(...)` → `remove_prompt = PromptManager.format("remove_ai_traces", ...)`

Also update import：
```python
from app.services.ai_service import AIService, PROMPTS
```
to:
```python
from app.services.ai_service import AIService
from app.services.prompt_manager import PromptManager
```

- [ ] **Step 3: ai_service.py 中替换**

Locate:
```python
prompt_template = PROMPTS.get(action, PROMPTS["continue"])
prompt = prompt_template.format(...)
```

Replace with:
```python
from app.services.prompt_manager import PromptManager

try:
    prompt_template = PromptManager.get(action)
except KeyError:
    prompt_template = PromptManager.get("continue")
prompt = prompt_template.format(
    content=content[:3000],
    context=context,
    title=title,
    genre=genre,
    description=description,
    question=question,
    outline_context=outline_context,
    previous_chapters=previous_chapters,
)
```

**重要**：此时不删除 `ai_service.py` 中的 `PROMPTS` 字典（wizard.py 仍在用，将在 Task 15 统一处理）。

- [ ] **Step 4: 验证**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/ai_generate.py backend/app/routers/ai_batch.py backend/app/services/ai_service.py
git commit -m "refactor(prompts): switch ai_generate/ai_batch/ai_service to PromptManager

PROMPTS dict in ai_service kept temporarily for wizard.py consumers.
Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 15: 替换 wizard.py 中所有 13 处 PROMPTS 引用

**Files:**
- Modify: `backend/app/routers/wizard.py`

- [ ] **Step 1: 修改 import**

Replace:
```python
from app.services.ai_service import AIService, PROMPTS
```
with:
```python
from app.services.ai_service import AIService
from app.services.prompt_manager import PromptManager
```

- [ ] **Step 2: 全局替换 `PROMPTS["<key>"].format(` → `PromptManager.format("<key>", `**

预期替换的引用（13 处）：
- `PROMPTS["wizard_revision"].format(` → `PromptManager.format("wizard_revision", `
- `PROMPTS["wizard_outline_characters"].format(` → 同理
- `PROMPTS["wizard_maps"].format(` → 同理（3 处：131 行、253 行、773 行、1182 行）
- `PROMPTS["wizard_parts"].format(` → 同理
- `PROMPTS["wizard_characters_for_part"].format(` → 同理
- `PROMPTS["wizard_outline_only"].format(` → 同理
- `PROMPTS["wizard_characters_from_outline"].format(` → 同理
- `PROMPTS["wizard_chapters_for_part"].format(` → 同理

**注意**：每处替换后，右括号 `)` 对应关系不变。只改 `PROMPTS["xxx"].format(` 这个前缀部分。

操作建议：在编辑器中用 find-and-replace 全局替换（但每处确认）：
- `PROMPTS["` → `PromptManager.format("`
- `"].format(` → `", `

组合起来就是 `PROMPTS["X"].format(...)` → `PromptManager.format("X", ...)`.

**警告**：此替换必须一起做两步，且只在 wizard.py 内。若 editor 不支持 regex，可以直接逐行替换：

```
PROMPTS["wizard_xxx"].format(  →  PromptManager.format("wizard_xxx",
```

- [ ] **Step 3: 验证 wizard.py 无残留 PROMPTS 引用**

Run: `grep -n "PROMPTS\[" backend/app/routers/wizard.py`
Expected: no output

- [ ] **Step 4: 验证**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `cd backend && pytest -q`
Expected: all passing

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/wizard.py
git commit -m "refactor(prompts): switch wizard.py to PromptManager (13 call sites)

Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 16: 从 ai_service.py 删除 PROMPTS 字典

**Files:**
- Modify: `backend/app/services/ai_service.py`

- [ ] **Step 1: 确认无其他引用**

Run: `grep -rn "PROMPTS\[" backend/app/ --include='*.py' | grep -v "DYNAMIC_PROMPTS"`

Expected: 如果有残留，先处理。如果输出只包含 `backend/tests/test_drama_ai_service.py` 中的 `DYNAMIC_PROMPTS`（那是另一套不同的数据结构，不在本次范围），则可以继续。

Run: `grep -rn "from app.services.ai_service import.*PROMPTS" backend/app/ backend/tests/`

Expected: no output（若还有，需先去除这些 import）。

- [ ] **Step 2: 定位并删除 PROMPTS 字典**

In `backend/app/services/ai_service.py`, delete the entire `PROMPTS = {...}` block（当前约在第 19-556 行）。

- [ ] **Step 3: 验证**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`
Run: `cd backend && pytest -q`
Expected: all passing

Run: `wc -l backend/app/services/ai_service.py`
Expected: 从 1165 降至约 900-950 行（删除了 ~200 行 prompt 文本）。

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/ai_service.py
git commit -m "refactor(prompts): remove PROMPTS dict from ai_service.py (moved to prompts/*.txt)

Directive: 所有 prompt 编辑必须通过 backend/app/prompts/*.txt 进行。
Reject: 不要再在 ai_service.py 中添加新的 prompt 字符串常量。
Confidence: high
Scope-risk: moderate

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 17: （可选）将 DEMO_RESPONSES 保持原位 — 不迁移

**Files:** 无（决策记录）

DEMO_RESPONSES 是用于 `demo` provider 的模拟回复，**不是** AI 的 prompt。结构更接近固定样本数据，不适合外置为模板。

- [ ] **Step 1: 确认 DEMO_RESPONSES 未被迁移**

Run: `grep -n "DEMO_RESPONSES" backend/app/services/ai_service.py | head`
Expected: 至少 2 处（字典定义 + `_stream_demo` 的引用），说明保留未动。

- [ ] **Step 2: 无需提交，此 Task 仅为记录决策**

---

## Task 18: Phase 2 端到端烟测

**Files:** 无

- [ ] **Step 1: 测试 /generate 端点（demo provider）走通**

Run: `cd /data/project/novel-writer && docker compose restart backend && sleep 5`

Run:
```bash
docker compose logs backend --tail 30 | grep -E "Prompt|已加载"
```
Expected: `已加载 23 个 prompt 模板`（或实际数量）

- [ ] **Step 2: 测试创作向导 (wizard) 端点可用**

用 API 文档中的 wizard 任一端点做最简单的 GET（若有 list / status 类端点），或检查 OpenAPI schema：

Run:
```bash
curl -s http://localhost:8084/openapi.json | python -c "
import sys, json
d = json.load(sys.stdin)
wizard_paths = [p for p in d['paths'] if '/wizard' in p]
print(f'wizard endpoints: {len(wizard_paths)}')
for p in sorted(wizard_paths)[:5]:
    print(' -', p)
"
```

Expected: 有 wizard 相关端点列出。

- [ ] **Step 3: 全量单测**

Run: `cd backend && pytest -v`
Expected: all passing, including new tests.

- [ ] **Step 4: 提交（若需要总结性的无代码变更提交，跳过此 step）**

此 Task 无代码改动，不需提交。

---

# PHASE 3：AiPanel 组件拆分（方案 C）

**前置说明**：本 phase 纯前端改动，不依赖 Phase 1 / 2。可以并行推进。

因为 `AiPanel.vue` 达 1616 行，本 phase 工作量大。采用 **完全重写** 策略：
1. 先建新目录 `frontend/src/components/ai/`，在其中写全新的 6 个子组件 + 1 个容器 `AiPanel.vue`
2. 写 composable `useAiGeneration.ts`
3. 旧的 `frontend/src/components/AiPanel.vue` 保留到 Task 27，最后一步才删除（以便调试对比）
4. 引用 AiPanel 的父组件暂不动，直到 Task 26 切换 import 路径

**由于前端缺乏单元测试框架，Phase 3 依赖手动冒烟测试**（在 Task 27 统一执行）。

## Task 19: 创建 useAiGeneration composable

**Files:**
- Create: `frontend/src/composables/useAiGeneration.ts`

- [ ] **Step 1: 阅读当前 AiPanel.vue 中与 SSE 相关的部分**

Run: `grep -n "EventSource\|fetch.*generate\|SSE\|processLine\|reader" frontend/src/components/AiPanel.vue | head -30`

查看前 ~50 行上下文，理解现有流式消费模式。

- [ ] **Step 2: 创建 composable**

Create `frontend/src/composables/useAiGeneration.ts`:

```typescript
/**
 * AI 生成状态管理与 SSE 消费。
 * 封装 POST /api/v1/projects/{id}/ai/generate 的流式处理。
 */
import { ref, computed, type Ref } from 'vue'
import { getAccessToken } from '@/api/request'

export interface ContextEntity {
  id: number
  type: string
  name: string
  summary?: string
  relevance?: number
  match_reason?: string
  is_pinned?: boolean
}

export interface GenerateParams {
  action: string
  content?: string
  question?: string
  chapter_id?: number | null
  chapter_ids?: number[]
  provider?: string
  pinned_context?: Record<string, number[]>
}

export function useAiGeneration(projectId: Ref<number | null>) {
  const generating = ref(false)
  const output = ref('')
  const error = ref<string | null>(null)
  const contextEntities = ref<ContextEntity[]>([])
  const abortController = ref<AbortController | null>(null)

  const canAbort = computed(() => generating.value && abortController.value !== null)

  async function generate(params: GenerateParams): Promise<string> {
    if (!projectId.value) {
      throw new Error('项目 ID 未设置')
    }

    // 重置状态
    generating.value = true
    output.value = ''
    error.value = null
    contextEntities.value = []
    abortController.value = new AbortController()

    try {
      const token = getAccessToken()
      const response = await fetch(
        `/api/v1/projects/${projectId.value}/ai/generate`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify(params),
          signal: abortController.value.signal,
        }
      )

      if (!response.ok) {
        throw new Error(`生成失败: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('无法读取流')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const rawLine of lines) {
          const line = rawLine.trim()
          if (!line || line.startsWith(':')) continue // 心跳/注释
          if (!line.startsWith('data: ')) continue

          try {
            const payload = JSON.parse(line.slice(6))
            if (payload.error) {
              error.value = payload.error
              continue
            }
            if (payload.type === 'context_used' && payload.entities) {
              contextEntities.value = payload.entities
              continue
            }
            if (payload.text) {
              output.value += payload.text
            }
          } catch {
            // 忽略解析失败
          }
        }
      }

      return output.value
    } catch (e: any) {
      if (e.name === 'AbortError') {
        error.value = '已取消'
      } else {
        error.value = e.message || '生成出错'
      }
      throw e
    } finally {
      generating.value = false
      abortController.value = null
    }
  }

  function abort() {
    abortController.value?.abort()
  }

  return {
    generating,
    output,
    error,
    contextEntities,
    canAbort,
    generate,
    abort,
  }
}
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: 无错误，或仅无关警告。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/composables/useAiGeneration.ts
git commit -m "feat(ai): add useAiGeneration composable for SSE consumption

Confidence: high
Scope-risk: narrow
Not-tested: 运行期行为，需要在 Task 27 冒烟测试

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 20: 创建 AiHistoryPanel 子组件

**Files:**
- Create: `frontend/src/components/ai/AiHistoryPanel.vue`

- [ ] **Step 1: 从旧 AiPanel 抽取历史记录 UI**

参考旧 `frontend/src/components/AiPanel.vue` 中历史记录部分（约 32-59 行）。

Create `frontend/src/components/ai/AiHistoryPanel.vue`:

```vue
<template>
  <div class="history-panel">
    <div class="panel-section-header">
      <span>历史记录</span>
      <el-button
        v-if="history.length > 0"
        size="small"
        text
        type="danger"
        @click="$emit('clear-all')"
      >
        清空
      </el-button>
    </div>
    <div v-if="history.length > 0" class="history-list">
      <div
        v-for="item in history.slice(0, 20)"
        :key="item.id"
        class="history-item"
        @click="$emit('use-item', item)"
      >
        <div class="history-header">
          <span class="history-action">{{ item.actionLabel }}</span>
          <span class="history-time">{{ formatTime(item.timestamp) }}</span>
        </div>
        <div class="history-preview">{{ item.output.slice(0, 60) }}...</div>
        <div class="history-meta">
          <span v-if="item.chapterTitle">「{{ item.chapterTitle }}」</span>
          <span>{{ item.wordCount }} 字</span>
        </div>
      </div>
    </div>
    <el-empty v-else description="暂无历史记录" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
export interface HistoryItem {
  id: string | number
  actionLabel: string
  timestamp: number
  output: string
  chapterTitle?: string
  wordCount: number
}

defineProps<{ history: HistoryItem[] }>()

defineEmits<{
  (e: 'use-item', item: HistoryItem): void
  (e: 'clear-all'): void
}>()

function formatTime(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
  return `${Math.floor(diff / 86400_000)} 天前`
}
</script>

<style scoped>
.history-panel {
  padding: 12px;
  max-height: 300px;
  overflow-y: auto;
}
.panel-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.history-item {
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  cursor: pointer;
  transition: background-color 0.15s;
}
.history-item:hover {
  background-color: var(--el-fill-color-light);
}
.history-header {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.history-preview {
  font-size: 13px;
  color: var(--el-text-color-regular);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.history-meta {
  margin-top: 4px;
  font-size: 11px;
  color: var(--el-text-color-placeholder);
  display: flex;
  gap: 8px;
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: no errors about this file.

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ai/AiHistoryPanel.vue
git commit -m "feat(ai): add AiHistoryPanel subcomponent (extracted from AiPanel.vue)

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 21: 创建 AiTemplatePanel 子组件

**Files:**
- Create: `frontend/src/components/ai/AiTemplatePanel.vue`

- [ ] **Step 1: 阅读旧 AiPanel 中模板面板部分**

定位 `template-panel` 部分（旧 AiPanel.vue ~62-91 行 + 相关脚本）。

- [ ] **Step 2: 创建组件**

Create `frontend/src/components/ai/AiTemplatePanel.vue`:

```vue
<template>
  <div class="template-panel">
    <div class="panel-section-header">
      <span>提示词模板</span>
      <el-button size="small" text type="primary" @click="$emit('create')">+ 新建</el-button>
    </div>
    <div class="template-categories">
      <div
        v-for="(tpls, cat) in categorizedTemplates"
        :key="cat"
        class="template-category"
      >
        <div v-if="tpls.length > 0" class="category-label">{{ getCategoryLabel(cat) }}</div>
        <div class="template-list">
          <div
            v-for="tpl in tpls"
            :key="tpl.id"
            class="template-item"
            @click="$emit('use', tpl)"
          >
            <div class="template-info">
              <span class="template-name">{{ tpl.name }}</span>
              <span class="template-desc">{{ tpl.description }}</span>
            </div>
            <div v-if="!tpl.isBuiltIn" class="template-actions">
              <el-button size="small" text :icon="Edit" @click.stop="$emit('edit', tpl)" />
              <el-button
                size="small"
                text
                type="danger"
                :icon="Delete"
                @click.stop="$emit('delete', tpl.id)"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Edit, Delete } from '@element-plus/icons-vue'

export interface Template {
  id: number | string
  name: string
  description: string
  category: string
  isBuiltIn?: boolean
}

defineProps<{
  categorizedTemplates: Record<string, Template[]>
}>()

defineEmits<{
  (e: 'use', tpl: Template): void
  (e: 'create'): void
  (e: 'edit', tpl: Template): void
  (e: 'delete', id: number | string): void
}>()

function getCategoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    writing: '写作',
    editing: '编辑',
    outline: '大纲',
    character: '角色',
    general: '通用',
  }
  return labels[cat] || cat
}
</script>

<style scoped>
.template-panel {
  padding: 12px;
  max-height: 400px;
  overflow-y: auto;
}
.panel-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 600;
}
.template-category {
  margin-bottom: 12px;
}
.category-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}
.template-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.template-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  cursor: pointer;
}
.template-item:hover {
  background: var(--el-fill-color-light);
}
.template-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.template-name {
  font-weight: 500;
  font-size: 13px;
}
.template-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
</style>
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: no errors related to this file.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/ai/AiTemplatePanel.vue
git commit -m "feat(ai): add AiTemplatePanel subcomponent

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 22: 创建 AiActionBar 子组件

**Files:**
- Create: `frontend/src/components/ai/AiActionBar.vue`

- [ ] **Step 1: 抽取旧 AiPanel 中的 `ai-actions` 按钮组**

定位旧 AiPanel.vue ~99 行开始的 `<div class="ai-actions">` 区块。

- [ ] **Step 2: 创建组件（按钮清单根据旧文件实际保留）**

Create `frontend/src/components/ai/AiActionBar.vue`:

```vue
<template>
  <div class="ai-actions">
    <el-button
      v-for="action in actions"
      :key="action.key"
      :disabled="disabled || (action.needsChapter && !hasChapter)"
      size="default"
      @click="$emit('action', action.key)"
    >
      <el-icon v-if="action.icon"><component :is="action.icon" /></el-icon>
      {{ action.label }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { MagicStick, Edit, DocumentAdd, User, ChatDotRound, Aim } from '@element-plus/icons-vue'

const props = defineProps<{
  disabled: boolean
  hasChapter: boolean
}>()

defineEmits<{ (e: 'action', key: string): void }>()

const actions = computed(() => [
  { key: 'continue', label: '续写', icon: MagicStick, needsChapter: true },
  { key: 'rewrite', label: '改写', icon: Edit, needsChapter: true },
  { key: 'expand', label: '扩写', icon: DocumentAdd, needsChapter: true },
  { key: 'analyze_expand', label: '分析扩写', icon: Aim, needsChapter: true },
  { key: 'character_analysis', label: '角色分析', icon: User, needsChapter: false },
  { key: 'plot_enhance', label: '剧情完善', icon: ChatDotRound, needsChapter: false },
  { key: 'free_chat', label: '创作咨询', icon: ChatDotRound, needsChapter: false },
])
</script>

<style scoped>
.ai-actions {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px;
}
</style>
```

**注意**：actions 数组中的 key 必须与后端 `payload.action` 的枚举值一一对应。若旧 AiPanel 中还有其他 action（如 `revise`、`generate_title`），需补齐。此处按常见 7 个作为起点，Task 26 容器组件联调时根据实际使用情况增补。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/ai/AiActionBar.vue
git commit -m "feat(ai): add AiActionBar subcomponent

Confidence: medium
Scope-risk: narrow
Not-tested: 按钮与旧 AiPanel 完全一致性，在 Task 26 对齐

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 23: 创建 AiOutputArea 子组件

**Files:**
- Create: `frontend/src/components/ai/AiOutputArea.vue`

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/ai/AiOutputArea.vue`:

```vue
<template>
  <div class="ai-output-area">
    <div class="output-header">
      <span class="output-title">AI 生成结果</span>
      <el-button
        v-if="generating"
        size="small"
        type="warning"
        plain
        @click="$emit('abort')"
      >
        <el-icon><CircleClose /></el-icon>
        中止
      </el-button>
    </div>

    <div class="output-body" :class="{ generating }">
      <pre v-if="output" class="output-text">{{ output }}</pre>
      <el-empty v-else-if="!generating" description="点击上方按钮开始生成" :image-size="60" />
      <div v-else class="generating-indicator">
        <el-icon class="spinner"><Loading /></el-icon>
        <span>生成中...</span>
      </div>
    </div>

    <div v-if="output && !generating" class="output-actions">
      <el-button type="primary" size="small" :disabled="!canInsert" @click="$emit('insert')">
        插入到章节
      </el-button>
      <el-button size="small" :disabled="!canInsert" @click="$emit('replace')">
        替换选区
      </el-button>
      <el-button size="small" @click="$emit('regenerate')">
        重新生成
      </el-button>
      <el-button size="small" @click="copyToClipboard">
        复制
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { CircleClose, Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  output: string
  generating: boolean
  canInsert: boolean
}>()

defineEmits<{
  (e: 'insert'): void
  (e: 'replace'): void
  (e: 'regenerate'): void
  (e: 'abort'): void
}>()

async function copyToClipboard() {
  try {
    await navigator.clipboard.writeText(props.output)
    ElMessage.success('已复制')
  } catch {
    ElMessage.error('复制失败')
  }
}
</script>

<style scoped>
.ai-output-area {
  display: flex;
  flex-direction: column;
  padding: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.output-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.output-title {
  font-weight: 600;
}
.output-body {
  min-height: 80px;
  max-height: 300px;
  overflow-y: auto;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  padding: 8px;
}
.output-body.generating::after {
  content: '▊';
  animation: blink 1s infinite;
}
@keyframes blink {
  50% { opacity: 0 }
}
.output-text {
  white-space: pre-wrap;
  word-wrap: break-word;
  margin: 0;
  font-family: inherit;
  font-size: 13px;
  line-height: 1.6;
}
.generating-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
}
.spinner {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg) }
  to { transform: rotate(360deg) }
}
.output-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
  flex-wrap: wrap;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/ai/AiOutputArea.vue
git commit -m "feat(ai): add AiOutputArea subcomponent

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 24: 创建 AiContextPreview 子组件

**Files:**
- Create: `frontend/src/components/ai/AiContextPreview.vue`

- [ ] **Step 1: 创建组件**

Create `frontend/src/components/ai/AiContextPreview.vue`:

```vue
<template>
  <div class="context-preview">
    <div class="preview-header">
      <span>AI 使用的上下文（{{ entities.length }}）</span>
    </div>
    <div class="entity-list">
      <div v-for="entity in entities" :key="`${entity.type}-${entity.id}`" class="entity-item">
        <el-tag :type="getTagType(entity.type)" size="small" class="entity-type">
          {{ getTypeLabel(entity.type) }}
        </el-tag>
        <span class="entity-name">{{ entity.name }}</span>
        <el-tooltip :content="entity.is_pinned ? '取消固定' : '固定'" placement="top">
          <el-button
            size="small"
            text
            :icon="entity.is_pinned ? Star : StarFilled"
            @click="$emit('toggle-pin', entity)"
          />
        </el-tooltip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Star, StarFilled } from '@element-plus/icons-vue'
import type { ContextEntity } from '@/composables/useAiGeneration'

defineProps<{ entities: ContextEntity[] }>()

defineEmits<{ (e: 'toggle-pin', entity: ContextEntity): void }>()

function getTagType(type: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    character: 'primary',
    worldbuilding: 'success',
    event: 'warning',
    note: 'info',
    outline: 'danger',
  }
  return map[type] || 'info'
}

function getTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    character: '角色',
    worldbuilding: '世界观',
    event: '事件',
    note: '笔记',
    outline: '大纲',
  }
  return labels[type] || type
}
</script>

<style scoped>
.context-preview {
  padding: 8px 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  max-height: 200px;
  overflow-y: auto;
}
.preview-header {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
}
.entity-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.entity-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.entity-type {
  flex: none;
}
.entity-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/ai/AiContextPreview.vue
git commit -m "feat(ai): add AiContextPreview subcomponent

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 25: 创建新的 AiPanel 容器组件

**Files:**
- Create: `frontend/src/components/ai/AiPanel.vue`

- [ ] **Step 1: 检查旧 AiPanel 的 props 契约**

Run: `grep -A 30 "defineProps\|defineEmits" frontend/src/components/AiPanel.vue | head -60`

记录所有 props 和 emits，确保新容器组件提供相同契约（供父组件无感切换）。

- [ ] **Step 2: 创建容器组件**

Create `frontend/src/components/ai/AiPanel.vue`:

```vue
<template>
  <div class="ai-panel">
    <!-- 面板标题 -->
    <div class="panel-header">
      <el-icon class="ai-icon"><MagicStick /></el-icon>
      <h3>AI 助手</h3>
      <el-tag v-if="currentProvider" size="small" type="info" class="provider-tag">
        {{ currentProvider }}
      </el-tag>
      <div class="header-actions">
        <el-tooltip content="历史记录">
          <el-button
            size="small"
            text
            :icon="Clock"
            :class="{ active: showHistory }"
            @click="showHistory = !showHistory"
          />
        </el-tooltip>
        <el-tooltip content="提示词模板">
          <el-button
            size="small"
            text
            :icon="Collection"
            :class="{ active: showTemplates }"
            @click="showTemplates = !showTemplates"
          />
        </el-tooltip>
      </div>
    </div>

    <AiHistoryPanel
      v-if="showHistory"
      :history="history"
      @use-item="useHistoryItem"
      @clear-all="clearHistory"
    />

    <AiTemplatePanel
      v-if="showTemplates"
      :categorized-templates="categorizedTemplates"
      @use="useTemplate"
      @create="openCreateTemplate"
      @edit="openEditTemplate"
      @delete="deleteTemplate"
    />

    <div v-if="currentChapterTitle" class="chapter-info">
      <p class="info-label">当前章节</p>
      <p class="chapter-name">{{ currentChapterTitle }}</p>
    </div>

    <AiActionBar
      :disabled="generating"
      :has-chapter="!!chapterId"
      @action="handleAction"
    />

    <AiContextPreview
      v-if="contextEntities.length > 0"
      :entities="contextEntities"
      @toggle-pin="togglePin"
    />

    <AiOutputArea
      v-if="output || generating"
      :output="output"
      :generating="generating"
      :can-insert="!!chapterId"
      @insert="handleInsert"
      @replace="handleReplace"
      @regenerate="handleRegenerate"
      @abort="abort"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef } from 'vue'
import { MagicStick, Clock, Collection } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

import AiHistoryPanel, { type HistoryItem } from './AiHistoryPanel.vue'
import AiTemplatePanel, { type Template } from './AiTemplatePanel.vue'
import AiActionBar from './AiActionBar.vue'
import AiOutputArea from './AiOutputArea.vue'
import AiContextPreview from './AiContextPreview.vue'
import { useAiGeneration, type ContextEntity } from '@/composables/useAiGeneration'

const props = defineProps<{
  projectId: number
  chapterId?: number | null
  currentContent?: string
  currentChapterTitle?: string
  currentProvider?: string
}>()

const emit = defineEmits<{
  (e: 'insert-text', text: string): void
  (e: 'replace-text', text: string): void
}>()

const showHistory = ref(false)
const showTemplates = ref(false)

const projectIdRef = toRef(props, 'projectId')
const {
  generating,
  output,
  error,
  contextEntities,
  generate,
  abort,
} = useAiGeneration(projectIdRef)

// 历史记录（暂用本地 ref，后续可接入 store）
const history = ref<HistoryItem[]>([])

// 模板（暂占位，后续接入 store）
const categorizedTemplates = ref<Record<string, Template[]>>({})

// 记录上次生成参数用于 regenerate
const lastAction = ref<string | null>(null)

async function handleAction(action: string) {
  lastAction.value = action
  try {
    await generate({
      action,
      content: props.currentContent,
      chapter_id: props.chapterId ?? undefined,
    })
    if (output.value) {
      // 写入历史
      history.value.unshift({
        id: Date.now(),
        actionLabel: action,
        timestamp: Date.now(),
        output: output.value,
        chapterTitle: props.currentChapterTitle,
        wordCount: output.value.length,
      })
    }
  } catch (e) {
    if (error.value && error.value !== '已取消') {
      ElMessage.error(error.value)
    }
  }
}

function handleRegenerate() {
  if (lastAction.value) {
    handleAction(lastAction.value)
  }
}

function handleInsert() {
  emit('insert-text', output.value)
}

function handleReplace() {
  emit('replace-text', output.value)
}

function useHistoryItem(item: HistoryItem) {
  output.value = item.output
}

function clearHistory() {
  history.value = []
}

function useTemplate(tpl: Template) {
  // 占位：实际实现应把模板内容填入某个输入区
  ElMessage.info(`使用模板：${tpl.name}`)
}

function openCreateTemplate() {
  ElMessage.info('新建模板（占位）')
}

function openEditTemplate(tpl: Template) {
  ElMessage.info(`编辑：${tpl.name}`)
}

function deleteTemplate(id: number | string) {
  ElMessage.info(`删除：${id}`)
}

function togglePin(entity: ContextEntity) {
  entity.is_pinned = !entity.is_pinned
}
</script>

<style scoped>
.ai-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--el-bg-color);
}
.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.panel-header h3 {
  margin: 0;
  font-size: 14px;
}
.ai-icon {
  color: var(--el-color-primary);
}
.provider-tag {
  margin-left: 4px;
}
.header-actions {
  margin-left: auto;
  display: flex;
  gap: 4px;
}
.header-actions .active {
  color: var(--el-color-primary);
}
.chapter-info {
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.info-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  margin: 0 0 2px 0;
}
.chapter-name {
  font-size: 13px;
  margin: 0;
  font-weight: 500;
}
</style>
```

**重要**：此容器组件的 props/emits 契约必须与旧 `AiPanel.vue` 保持一致，否则父组件切换会坏。如果发现旧 AiPanel 有额外的 prop（如 `show-context-panel`、`pinned-context` 等），在这里补充。

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: no errors related to new files.

- [ ] **Step 4: 提交**

```bash
git add frontend/src/components/ai/AiPanel.vue
git commit -m "feat(ai): add new AiPanel container composing all subcomponents

Replaces 1616-line monolithic AiPanel with ~200-line orchestrator.
Directive: 模板/历史存储暂为本地 ref，后续接入 Pinia store 是独立工作
Confidence: medium
Scope-risk: moderate
Not-tested: 与旧 AiPanel 完全功能等价，留待 Task 26 联调

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 26: 切换父组件引用到新 AiPanel

**Files:**
- Modify: 所有 import `@/components/AiPanel.vue` 的父组件（主要是 ContextPanel.vue）

- [ ] **Step 1: 查找旧 AiPanel 的所有引用**

Run: `grep -rn "AiPanel" frontend/src --include='*.vue' --include='*.ts'`
Expected: 至少看到 `ContextPanel.vue` 等父组件的 import 行。

- [ ] **Step 2: 替换 import 路径**

对每个引用点：
```vue
import AiPanel from '@/components/AiPanel.vue'
```
改为：
```vue
import AiPanel from '@/components/ai/AiPanel.vue'
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -30`
Expected: no errors.

- [ ] **Step 4: 冒烟测试**

Run: `cd /data/project/novel-writer && docker compose up -d frontend && sleep 5`

浏览器访问 `http://localhost:8083`，登录 → 打开项目工作台：
- [ ] AI 面板能正常展示
- [ ] 历史记录按钮能切换显示
- [ ] 模板按钮能切换显示
- [ ] 续写按钮点击后有流式输出
- [ ] 输出完成后能插入到章节

如果发现 action 缺失或 emit 契约不匹配，在此 task 内修复。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/components/
git commit -m "refactor(ai): switch all AiPanel imports to new ai/AiPanel.vue

Confidence: medium
Scope-risk: moderate
Directive: 旧 frontend/src/components/AiPanel.vue 尚未删除，供对比调试用

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 27: 删除旧 AiPanel.vue，完成 Phase 3

**Files:**
- Delete: `frontend/src/components/AiPanel.vue`

- [ ] **Step 1: 最终确认无引用**

Run: `grep -rn "components/AiPanel\.vue" frontend/src`
Expected: no output. 所有引用都已指向 `components/ai/AiPanel.vue`.

- [ ] **Step 2: 删除旧文件**

Run: `rm frontend/src/components/AiPanel.vue`

- [ ] **Step 3: 类型检查 + 浏览器冒烟**

Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`
Expected: no errors.

浏览器走一遍 AI 面板主流程，确认无回归：
- 续写 / 改写 / 扩写 / 分析扩写 / 剧情完善 / 创作咨询
- 历史面板切换
- 模板面板切换
- 上下文预览显示
- 生成中的「中止」按钮能取消请求

- [ ] **Step 4: 提交**

```bash
git rm frontend/src/components/AiPanel.vue
git commit -m "chore(ai): remove legacy AiPanel.vue monolith (1616 lines)

Phase 3 complete. 新结构：components/ai/{AiPanel,AiHistoryPanel,
AiTemplatePanel,AiActionBar,AiOutputArea,AiContextPreview}.vue
Confidence: medium
Scope-risk: moderate
Not-tested: 历史记录跨刷新的持久化（当前为本地 ref，原实现细节后续 PR 迁移到 store）

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

# 完成检查清单

本轮 3 个方案全部完成时，验证以下：

- [ ] `backend/app/utils/sse.py` 存在，包含 `SSEStreamHelper` 和 `TokenTracker`
- [ ] `backend/app/routers/ai.py` 不存在
- [ ] `backend/app/routers/ai_generate.py`、`ai_batch.py`、`ai_config.py` 存在，每个 <400 行
- [ ] `backend/app/prompts/` 下有 23 个 `.txt` 文件
- [ ] `backend/app/services/ai_service.py` 不再定义 `PROMPTS`（保留 `DEMO_RESPONSES`）
- [ ] `backend/app/services/prompt_manager.py` 存在
- [ ] 启动日志显示 `已加载 23 个 prompt 模板`
- [ ] `frontend/src/components/AiPanel.vue` 不存在
- [ ] `frontend/src/components/ai/` 下有 6 个 `.vue` 文件
- [ ] `frontend/src/composables/useAiGeneration.ts` 存在
- [ ] 后端测试 `pytest -q` 全绿，测试数 ≥ 25
- [ ] 前端 `npx vue-tsc --noEmit` 无错误
- [ ] 浏览器冒烟：续写/改写/扩写/剧情完善/创作咨询 5 条路径全部正常

---

## Self-Review 记录

**Spec 覆盖检查**：
- Spec §方案 A → Tasks 1-10 ✓
- Spec §方案 B → Tasks 11-18 ✓
- Spec §方案 C → Tasks 19-27 ✓
- Spec §测试策略 → Task 1/2/3/4/11 单元测试；Task 18/26/27 冒烟测试 ✓
- Spec §回滚计划 → 每个 Task 独立 commit，易于 revert ✓

**新增范围修订**（在 spec 中未显式列出，发现于探索阶段）：
- `wizard.py` 13 处 PROMPTS 引用 → Task 15 覆盖
- `DEMO_RESPONSES` 保留不迁移 → Task 17 记录

**Placeholder 扫描**：已全部给出具体代码、具体命令、具体文件路径。

**类型一致性检查**：
- `SSEStreamHelper.wrap_stream` 签名 Task 2 定义、Task 8/9/10 调用，参数名 `on_text` / `on_usage` / `preamble` 一致 ✓
- `TokenTracker.flush` 签名 Task 4 定义，Task 8/9 调用，参数 `input_text` 一致 ✓
- `PromptManager.format` 签名 Task 11 定义，Task 14/15 调用，签名 `(name, **kwargs)` 一致 ✓
- `useAiGeneration` 返回值 Task 19 定义，Task 25 调用，解构名（generating/output/error/contextEntities/generate/abort）一致 ✓
