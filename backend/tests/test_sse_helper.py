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
