"""style_guide_extractor 抽取服务测试 —— 全部 mock LLM"""
import json
import pytest

from app.services import style_guide_extractor


VALID_LLM_OUTPUT = json.dumps({
    "structured": {
        "pov": "第一人称",
        "tense": "过去时",
        "sentence_length": "短句为主",
        "dialogue_density": "high",
        "pacing": "强反转密集",
        "opening_formula": "倒叙抛悬念",
        "ending_formula": "高甜余韵",
        "signature_devices": ["内心独白", "短段落分隔"],
    },
    "prose_excerpt": "一段示范原文文本，约一百多字。" * 8,
    "prompt_fragment": "用第一人称过去时，短句为主……约三百字。" * 3,
}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_extract_returns_parsed_guide(monkeypatch):
    async def fake_gen(prompt, provider=None, max_tokens=None):
        return VALID_LLM_OUTPUT

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    guide_json, model = await style_guide_extractor.extract("《标题》", "正文" * 100)
    parsed = json.loads(guide_json)
    assert parsed["structured"]["pov"] == "第一人称"
    assert len(parsed["prose_excerpt"]) >= 100
    assert isinstance(model, str) and model


@pytest.mark.asyncio
async def test_extract_raises_on_invalid_json(monkeypatch):
    async def fake_gen(prompt, provider=None, max_tokens=None):
        return "这不是 json 也不是 markdown"

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    with pytest.raises(style_guide_extractor.StyleGuideExtractionError):
        await style_guide_extractor.extract("t", "c")


@pytest.mark.asyncio
async def test_extract_strips_markdown_code_fence(monkeypatch):
    """允许 LLM 套了 ```json 围栏，应能剥掉再解析"""
    fenced = f"```json\n{VALID_LLM_OUTPUT}\n```"

    async def fake_gen(prompt, provider=None, max_tokens=None):
        return fenced

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    guide_json, _ = await style_guide_extractor.extract("t", "c")
    parsed = json.loads(guide_json)
    assert parsed["structured"]["pov"] == "第一人称"
