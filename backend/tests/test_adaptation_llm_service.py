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
async def test_rewrite_scene_two_pass_uses_skeleton():
    """intensity>=2 应走 two-pass：Pass1 抽骨架/金句，Pass2 基于骨架重写。"""
    fake_provider = AsyncMock()
    prompts: list[str] = []

    async def fake_complete(prompt: str, **kw):
        prompts.append(prompt)
        if len(prompts) == 1:
            # Pass1：返回合法骨架 JSON
            return json.dumps({
                "skeleton": "开场陆父逼林尘签字 → 林尘表面顺从 → 林尘反转觉醒",
                "golden_lines": ["哦。", "成了。"],
                "scene_beats": [
                    {"beat": "陆父发难", "characters": ["陆父", "林尘"], "emotion": "压抑"},
                    {"beat": "林尘觉醒", "characters": ["林尘"], "emotion": "爆发"},
                ],
            })
        return "重写后的本场内容"

    fake_provider.complete = fake_complete
    svc = AdaptationLLMService(provider=fake_provider)

    out = await svc.rewrite_scene(
        scene_text="原文很长……",
        intensity=3,
        intent="时代搬到 80 年代",
        era_target="80 年代",
        mappings=[
            {"original_text": "老张", "replacement_text": "老陈", "locked": True, "entity_type": "person"},
        ],
        prev_scene_summary=None,
        character_traits=[],
        extra_prompt=None,
        scene_title="1-1 开场",
    )
    assert out == "重写后的本场内容"
    assert len(prompts) == 2, "two-pass 应当调用 provider.complete 两次"
    # Pass1 prompt 应当包含原文与骨架抽取指令
    assert "剧情骨架" in prompts[0]
    assert "原文很长" in prompts[0]
    # Pass2 prompt 应当包含骨架/金句/映射表，并且不包含原文
    assert "陆父发难" in prompts[1] or "陆父" in prompts[1]
    assert "哦。" in prompts[1]
    assert "[LOCKED]" in prompts[1] and "老陈" in prompts[1]
    assert "原文很长" not in prompts[1], "Pass2 不应将原文传入，必须基于骨架重写"


@pytest.mark.asyncio
async def test_rewrite_scene_two_pass_falls_back_when_pass1_invalid():
    """Pass1 返回非 JSON 时应回退到纯实体替换 body（intensity=1 prompt），不走删 2 留 1。"""
    fake_provider = AsyncMock()
    prompts: list[str] = []

    async def fake_complete(prompt: str, **kw):
        prompts.append(prompt)
        if len(prompts) == 1:
            return "不是 JSON"
        return "回退改写内容"

    fake_provider.complete = fake_complete
    svc = AdaptationLLMService(provider=fake_provider)

    out = await svc.rewrite_scene(
        scene_text="原文",
        intensity=2,
        intent=None,
        era_target=None,
        mappings=[],
        prev_scene_summary=None,
        character_traits=[],
        extra_prompt=None,
    )
    assert out == "回退改写内容"
    # 回退路径必须用 intensity=1 的精准替换 body，不能带"删配角整行"等激进指令
    fallback_prompt = prompts[1]
    assert "你只做精准的实体替换" in fallback_prompt
    assert "删除" not in fallback_prompt or "整行删除" not in fallback_prompt


@pytest.mark.asyncio
async def test_rewrite_scene_strips_code_fence():
    """LLM 若把结果包在 ```...``` 围栏里，rewrite_scene 出口应剥离。"""
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="```\n改写后内容\n```")
    svc = AdaptationLLMService(provider=fake_provider)
    out = await svc.rewrite_scene(
        scene_text="原文",
        intensity=1,
        intent=None,
        era_target=None,
        mappings=[],
        prev_scene_summary=None,
        character_traits=[],
        extra_prompt=None,
    )
    assert out == "改写后内容"


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
