"""改编 LLM 服务层测试（mock provider）。"""
import json
import pytest
from unittest.mock import AsyncMock

from app.services.adaptation_llm_service import AdaptationLLMService


@pytest.mark.asyncio
async def test_extract_entities_parses_json():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value=json.dumps({
        "entities": [{"type": "person", "text": "李铁柱", "count": 5, "sample_context": "..."}],
        "character_traits": [{"name": "李铁柱", "tags": ["重情义"]}],
    }))
    svc = AdaptationLLMService(provider=fake_provider)
    out = await svc.extract_entities("一段原文")
    assert out["entities"][0]["text"] == "李铁柱"
    assert out["character_traits"][0]["tags"] == ["重情义"]


@pytest.mark.asyncio
async def test_extract_entities_invalid_json_raises():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="不是 JSON")
    svc = AdaptationLLMService(provider=fake_provider)
    with pytest.raises(ValueError):
        await svc.extract_entities("x")


@pytest.mark.asyncio
async def test_rewrite_scene_includes_locked_marker():
    fake_provider = AsyncMock()
    captured = {}

    async def fake_complete(prompt: str, **kw):
        captured["prompt"] = prompt
        return "改写后的场内容"

    fake_provider.complete = fake_complete
    svc = AdaptationLLMService(provider=fake_provider)

    out = await svc.rewrite_scene(
        scene_text="原文场",
        intensity=3,
        intent="搬到 1990 上海",
        era_target="1990 上海",
        mappings=[
            {"original_text": "李铁柱", "replacement_text": "陈豪", "locked": True, "entity_type": "person"},
            {"original_text": "长安", "replacement_text": "上海", "locked": False, "entity_type": "place"},
        ],
        prev_scene_summary="主角与师父告别",
        character_traits=[{"name": "李铁柱", "tags": ["重情义"]}],
        extra_prompt=None,
    )
    assert out == "改写后的场内容"
    assert "[LOCKED]" in captured["prompt"]
    assert "李铁柱" in captured["prompt"] and "陈豪" in captured["prompt"]
    assert "1990" in captured["prompt"]


@pytest.mark.asyncio
async def test_split_by_llm_parses_offset_array():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value=json.dumps([
        {"start": 0, "end": 10, "title": "场A"},
        {"start": 10, "end": 25, "title": "场B"},
    ]))
    svc = AdaptationLLMService(provider=fake_provider)
    bs = await svc.split_by_llm("一段没场标记的文本，凑长度到二十五个字符。")
    assert len(bs) == 2
    assert bs[0].title == "场A"
    assert bs[1].end == 25
