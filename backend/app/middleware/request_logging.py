"""
请求日志中间件
记录所有 API 请求和响应信息，便于问题排查
"""
import json
import time
import logging
from typing import Callable
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse

logger = logging.getLogger("api_logger")

# 不记录请求体的路径（避免记录大文件或敏感数据）
SKIP_BODY_PATHS = [
    "/api/v1/ai/",  # AI 相关接口可能有大文本
]

# 不记录响应体的路径
SKIP_RESPONSE_BODY_PATHS = [
    "/api/v1/wizard/generate",  # SSE 流式接口
    "/api/v1/wizard/generate-maps",
    "/api/v1/wizard/generate-parts",
    "/api/v1/wizard/generate-characters",
    "/api/v1/wizard/generate-characters-for-part",
    "/api/v1/wizard/generate-outline",
    "/api/v1/ai/write-chapter",
    "/api/v1/ai/chat",
]

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
            # 美化 JSON，但限制长度
            formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
            return truncate_body(formatted)
        except json.JSONDecodeError:
            return truncate_body(decoded)
    except UnicodeDecodeError:
        return f"<binary data, {len(body)} bytes>"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    请求日志中间件

    记录每个请求的：
    - 请求方法和路径
    - 请求头（可选）
    - 请求体
    - 响应状态码
    - 响应体（可选）
    - 处理时间
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 跳过健康检查等静态请求
        if request.url.path in ["/", "/favicon.ico"] or request.url.path.startswith("/assets"):
            return await call_next(request)

        # 获取请求 ID
        request_id = getattr(request.state, "request_id", "unknown")

        # 记录开始时间
        start_time = time.time()

        # 收集请求信息
        request_info = {
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) or None,
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", ""),
        }

        # 记录请求体（仅 POST/PUT/PATCH）
        should_log_body = not any(
            request.url.path.startswith(p) for p in SKIP_BODY_PATHS
        )

        if should_log_body and request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            try:
                body = await request.body()
                if body:
                    request_info["body"] = safe_json_loads(body)
            except Exception as e:
                request_info["body_error"] = str(e)

        # 打印请求日志
        logger.info(f"--> {request_info['method']} {request_info['path']} | "
                   f"client: {request_info['client_ip']} | "
                   f"body: {request_info.get('body', 'N/A')}")

        # 调用下一个处理器
        response = await call_next(request)

        # 计算处理时间
        process_time = (time.time() - start_time) * 1000

        # 记录响应信息
        response_info = {
            "request_id": request_id,
            "status_code": response.status_code,
            "process_time_ms": round(process_time, 2),
        }

        # 记录响应体（非流式响应）
        should_log_response = not any(
            request.url.path.startswith(p) for p in SKIP_RESPONSE_BODY_PATHS
        )

        if should_log_response and not isinstance(response, StreamingResponse):
            try:
                # 获取响应体
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk

                # 重新包装响应体以便返回
                from fastapi.responses import Response as FastAPIResponse

                new_response = FastAPIResponse(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

                if response_body:
                    response_info["response"] = safe_json_loads(response_body)

            except Exception as e:
                response_info["response_error"] = str(e)
                new_response = response
        else:
            new_response = response
            if isinstance(response, StreamingResponse):
                response_info["response"] = "<streaming response>"

        # 打印响应日志
        status_emoji = "✓" if response.status_code < 400 else "✗"
        logger.info(f"<-- {status_emoji} {response_info['status_code']} | "
                   f"time: {response_info['process_time_ms']}ms | "
                   f"response: {response_info.get('response', 'N/A')}")

        return new_response