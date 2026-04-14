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
