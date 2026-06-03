"""canon_pipeline 纯函数单测（不触发 LLM）"""
import pytest
from unittest.mock import patch, AsyncMock

from app.services.ai_service import AIService
from app.services.canon_pipeline import _chunk_reference, _safe_json_array


def test_chunk_reference_splits_long_text():
    content = "\n".join([f"第{i}段内容，约二十个汉字凑数填充。" for i in range(50)])
    chunks = _chunk_reference(content, chunk_size=200)
    assert len(chunks) > 1
    # 每块带 label
    assert all("label" in c and "text" in c for c in chunks)
    assert chunks[0]["label"].startswith("片段")


def test_safe_json_array_parses_fenced():
    raw = '```json\n[{"canonical_name":"孙悟空","entity_type":"character"}]\n```'
    arr = _safe_json_array(raw)
    assert len(arr) == 1
    assert arr[0]["canonical_name"] == "孙悟空"


def test_safe_json_array_returns_empty_on_garbage():
    assert _safe_json_array("这不是JSON，纯文本。") == []


async def test_atomic_extract_one_chunk_parses_entities():
    from app.services.canon_pipeline import _atomic_extract_chunk

    fake_llm = AsyncMock(return_value=(
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source":{"quote":"我本是乌鸡国王"},"importance":"major"}]'
    ))
    with patch.object(AIService, "generate_text", fake_llm):
        ents = await _atomic_extract_chunk(
            {"label": "第三十七回", "text": "我本是乌鸡国王..."}, model=None
        )
    assert len(ents) == 1
    assert ents[0]["canonical_name"] == "乌鸡国国王"
    # source 被规整进 source_refs
    assert ents[0]["source_refs"][0]["quote"] == "我本是乌鸡国王"
    assert ents[0]["source_refs"][0]["chapter"] == "第三十七回"


async def test_atomic_extract_chunk_handles_bad_json():
    from app.services.canon_pipeline import _atomic_extract_chunk
    with patch.object(AIService, "generate_text", AsyncMock(return_value="抱歉我无法解析")):
        ents = await _atomic_extract_chunk({"label": "片段1", "text": "x"}, model=None)
    assert ents == []


async def test_merge_entities_by_type_disambiguates():
    from app.services.canon_pipeline import _merge_entities_of_type

    raw = [
        {"entity_type": "character", "canonical_name": "乌鸡国王",
         "aliases": ["陛下"], "source_refs": [{"chapter": "片段1", "quote": "a"}]},
        {"entity_type": "character", "canonical_name": "乌鸡国国王",
         "aliases": [], "source_refs": [{"chapter": "片段2", "quote": "b"}]},
    ]
    merged_json = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下","乌鸡国王"],"summary":"被害君主",'
        '"source_refs":[{"chapter":"片段1","quote":"a"},{"chapter":"片段2","quote":"b"}],'
        '"importance":"major"}]'
    )
    with patch.object(AIService, "generate_text", AsyncMock(return_value=merged_json)):
        merged = await _merge_entities_of_type("character", raw, model=None)
    assert len(merged) == 1
    assert merged[0]["canonical_name"] == "乌鸡国国王"
    assert len(merged[0]["source_refs"]) == 2


async def test_merge_entities_empty_returns_empty():
    from app.services.canon_pipeline import _merge_entities_of_type
    assert await _merge_entities_of_type("ability", [], model=None) == []
