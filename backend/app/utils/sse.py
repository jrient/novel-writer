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
        preamble: Optional[list] = None,
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
        self._collected_text: list = []
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
