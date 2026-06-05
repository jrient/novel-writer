"""canon prompts：模板渲染含必填指令"""
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt


def test_atomic_prompt_contains_chunk_and_sourcing_rule():
    p = build_atomic_prompt(chunk_text="乌鸡国国王被推入井中。", chunk_label="第三十七回")
    assert "乌鸡国国王被推入井中" in p
    assert "第三十七回" in p
    assert "quote" in p          # 要求附原文引用
    assert "JSON" in p


def test_merge_prompt_groups_by_type():
    raw = [
        {"entity_type": "character", "canonical_name": "乌鸡国王", "aliases": ["陛下"]},
        {"entity_type": "character", "canonical_name": "乌鸡国国王", "aliases": []},
    ]
    p = build_merge_prompt(entity_type="character", raw_entities=raw)
    assert "乌鸡国王" in p
    assert "乌鸡国国王" in p
    assert "合并" in p or "归并" in p

def test_atomic_prompt_includes_new_dimensions():
    p = build_atomic_prompt(chunk_text="他取出一件法宝", chunk_label="片段1")
    for key in ("item", "race", "realm", "concept"):
        assert key in p
    # 中文维度名也应出现在类型说明里
    assert "物品" in p and "种族" in p and "境界" in p and "术语" in p
