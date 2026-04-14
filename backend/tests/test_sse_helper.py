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
