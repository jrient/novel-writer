"""StyleSample chunk 切分 + 索引服务测试"""
import pytest

from app.services.style_sample_indexer import split_chunks


def test_split_chunks_short_text_single():
    """短文本只产 1 个 chunk，即使少于 100 字也保留"""
    text = "短短的一段。"
    chunks = split_chunks(text)
    assert len(chunks) == 1
    assert chunks[0] == "短短的一段。"


def test_split_chunks_by_paragraph():
    """段落已经在 100-500 字内，按段切，不合并不切分"""
    p1 = "第一段。" * 50   # 200 字
    p2 = "第二段。" * 60   # 240 字
    text = f"{p1}\n\n{p2}"
    chunks = split_chunks(text)
    assert len(chunks) == 2
    assert chunks[0] == p1
    assert chunks[1] == p2


def test_split_chunks_merge_short_with_next():
    """少于 100 字的段并入下一段"""
    short = "短段。" * 10                # 30 字
    next_p = "下一段。" * 50              # 200 字
    text = f"{short}\n\n{next_p}"
    chunks = split_chunks(text)
    assert len(chunks) == 1
    assert chunks[0].startswith(short)
    assert chunks[0].endswith(next_p)


def test_split_chunks_hard_split_long_at_sentence_end():
    """超 500 字的段在 500 字往前找句末符切；找不到才硬切"""
    text = "一" * 480 + "。" + "二" * 200 + "。"
    chunks = split_chunks(text)
    assert len(chunks) == 2
    assert chunks[0].endswith("。")
    assert len(chunks[0]) <= 500
    assert chunks[1].startswith("二")


def test_split_chunks_hard_split_no_sentence_mark():
    """500 字内无句末符 → 硬切到 500"""
    text = "甲" * 700  # 全角无标点
    chunks = split_chunks(text)
    assert len(chunks) == 2
    assert len(chunks[0]) == 500
    assert len(chunks[1]) == 200


def test_split_chunks_trailing_short_orphan():
    """最后一段少于 100 字且没有下一段可合 —— 允许独立"""
    p1 = "主段。" * 60
    short = "尾。"
    text = f"{p1}\n\n{short}"
    chunks = split_chunks(text)
    assert short in chunks
