"""canon_pipeline 纯函数单测（不触发 LLM）"""
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
