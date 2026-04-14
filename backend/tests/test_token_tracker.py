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
        assert est_mock.call_count == 2
