"""
请求日志中间件（纯 ASGI 实现）
记录所有 API 请求和响应信息，便于问题排查
SSE 流式接口直接透传，不做任何缓冲
"""
import json
import time
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("api_logger")

# 不记录请求体的路径（避免记录大文件或敏感数据）
SKIP_BODY_PATHS = [
    "/api/v1/ai/",
]

# SSE 流式接口路径关键词，直接透传不做处理
SSE_PATH_KEYWORDS = ["/ai/generate", "/ai/batch-generate", "/session/answer", "/session/generate-outline", "/expand", "/ai/rewrite", "/ai/global-directive"]

# 跳过日志的路径
SKIP_PATHS = ["/", "/favicon.ico"]

# 最大记录的请求/响应体长度
MAX_BODY_LENGTH = 2000


def truncate_body(body: str, max_length: int = MAX_BODY_LENGTH) -> str:
    """截断过长的内容"""
    if len(body) > max_length:
        return body[:max_length] + f"... (truncated, total {len(body)} chars)"
    return body


def safe_json_loads(body: bytes) -> str:
    """安全解析 JSON，失败则返回原始字符串"""
    try:
        decoded = body.decode("utf-8")
        try:
            parsed = json.loads(decoded)
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
            return truncate_body(formatted)
        except json.JSONDecodeError:
            return truncate_body(decoded)
    except UnicodeDecodeError:
        return f"<binary data, {len(body)} bytes>"


class RequestLoggingMiddleware:
    """
    纯 ASGI 请求日志中间件，不缓冲流式响应
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # 跳过静态路径
        if path in SKIP_PATHS or path.startswith("/assets"):
            await self.app(scope, receive, send)
            return

        # SSE 流式接口直接透传，避免任何缓冲
        if any(kw in path for kw in SSE_PATH_KEYWORDS):
            await self.app(scope, receive, send)
            return

        # 获取请求信息
        request_id = scope.get("state", {}).get("request_id", "unknown")
        method = scope.get("method", "?")
        client = scope.get("client", ("unknown", 0))
        client_ip = client[0] if client else "unknown"

        start_time = time.time()

        # 记录请求
        logger.info(f"[{request_id}] --> {method} {path} | client: {client_ip} | body: N/A")

        # 拦截响应以记录状态码
        status_code = [0]

        async def send_with_logging(message):
            if message["type"] == "http.response.start":
                status_code[0] = message.get("status", 0)
            elif message["type"] == "http.response.body":
                if status_code[0]:
                    process_time = (time.time() - start_time) * 1000
                    status_emoji = "✓" if status_code[0] < 400 else "✗"
                    body = message.get("body", b"")
                    response_text = safe_json_loads(body) if body and len(body) < MAX_BODY_LENGTH * 2 else "N/A"
                    logger.info(
                        f"[{request_id}] <-- {status_emoji} {status_code[0]} | "
                        f"time: {round(process_time, 2)}ms | response: {response_text}"
                    )
            await send(message)

        await self.app(scope, receive, send_with_logging)
