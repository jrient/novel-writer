"""
请求追踪中间件
为每个 API 请求生成唯一 ID，便于日志追踪和问题排查
"""
import uuid
import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

# 请求 ID 头名称
REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    请求 ID 中间件

    为每个请求生成唯一 ID，并：
    1. 注入到请求状态中
    2. 添加到响应头中
    3. 注入到日志上下文中
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成或获取请求 ID
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())

        # 存储到请求状态
        request.state.request_id = request_id

        # 注入到日志上下文
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            record.request_id = request_id
            return record

        logging.setLogRecordFactory(record_factory)

        try:
            # 处理请求
            response = await call_next(request)

            # 添加请求 ID 到响应头
            response.headers[REQUEST_ID_HEADER] = request_id

            return response

        finally:
            # 恢复原始日志工厂
            logging.setLogRecordFactory(old_factory)


def get_request_id(request: Request) -> str:
    """
    从请求中获取请求 ID

    Args:
        request: FastAPI 请求对象

    Returns:
        str: 请求 ID
    """
    return getattr(request.state, "request_id", "unknown")