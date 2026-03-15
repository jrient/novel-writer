"""
请求追踪中间件（纯 ASGI 实现）
为每个 API 请求生成唯一 ID，便于日志追踪和问题排查
"""
import uuid
import logging

from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)

# 请求 ID 头名称
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """
    纯 ASGI 请求 ID 中间件，不缓冲流式响应
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 从请求头获取或生成请求 ID
        headers = dict(scope.get("headers", []))
        request_id = None
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == "x-request-id":
                request_id = value.decode("latin-1")
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        # 存储到 scope state
        if "state" not in scope:
            scope["state"] = {}
        scope["state"]["request_id"] = request_id

        # 注入请求 ID 到响应头
        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def get_request_id(request: Request) -> str:
    """从请求中获取请求 ID"""
    return getattr(request.state, "request_id", "unknown")
