"""场切分服务测试：仅测正则路径，LLM fallback 在 pipeline 测试中通过 mock 走。"""
import pytest
from app.services.adaptation_splitter import split_by_regex, SceneBoundary


def test_regex_chinese_scenes():
    text = "场1 长安城外\n李铁柱挥剑。\n场2 客栈\n二人对饮。"
    boundaries = split_by_regex(text)
    assert len(boundaries) == 2
    assert boundaries[0].title.startswith("场1")
    assert text[boundaries[0].start:boundaries[0].end].startswith("场1")
    assert text[boundaries[1].start:boundaries[1].end].startswith("场2")


def test_regex_int_ext_scenes():
    text = "INT. CAFE - DAY\nMark sips coffee.\nEXT. STREET - NIGHT\nRain falls."
    boundaries = split_by_regex(text)
    assert len(boundaries) == 2
    assert boundaries[0].title.startswith("INT.")


def test_regex_too_few_returns_empty():
    text = "场1 仅一场\n剩下都是正文"
    assert split_by_regex(text) == []


def test_regex_no_match_returns_empty():
    assert split_by_regex("毫无场标记的散文") == []


def test_boundaries_cover_text_continuously():
    text = "场1 a\n111\n场2 b\n222\n场3 c\n333"
    bs = split_by_regex(text)
    assert len(bs) == 3
    assert bs[0].start == 0
    assert bs[-1].end == len(text)
    for prev, nxt in zip(bs, bs[1:]):
        assert prev.end == nxt.start
