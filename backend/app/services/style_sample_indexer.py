"""StyleSample 索引服务：chunk 切分 + embedding 写入

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第六节。
"""
from typing import List

CHUNK_MIN = 100
CHUNK_MAX = 500
SENTENCE_END_MARKS = "。！？…"


def _hard_split_long_paragraph(text: str) -> List[str]:
    """超 CHUNK_MAX 的段落硬切：先找 CHUNK_MAX 内最后的句末符，没有就切到 CHUNK_MAX。"""
    out: List[str] = []
    remaining = text
    while len(remaining) > CHUNK_MAX:
        window = remaining[:CHUNK_MAX]
        cut = -1
        for i in range(CHUNK_MAX - 1, CHUNK_MAX - 101, -1):
            if i < 0:
                break
            if window[i] in SENTENCE_END_MARKS:
                cut = i + 1
                break
        if cut == -1:
            cut = CHUNK_MAX
        out.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        out.append(remaining)
    return out


def split_chunks(content: str) -> List[str]:
    """按段落切分，少 100 字段并入下一段，超 500 字按句末符硬切。

    规则详见 spec 第六节。
    """
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    refined: List[str] = []
    for p in paragraphs:
        refined.extend(s.strip() for s in p.split("\n") if s.strip())

    if not refined:
        return []

    merged: List[str] = []
    buffer = ""
    for p in refined:
        if buffer:
            buffer = buffer + p
            if len(buffer) >= CHUNK_MIN:
                merged.append(buffer)
                buffer = ""
        elif len(p) < CHUNK_MIN:
            buffer = p
        else:
            merged.append(p)
    if buffer:
        merged.append(buffer)

    out: List[str] = []
    for p in merged:
        if len(p) > CHUNK_MAX:
            out.extend(_hard_split_long_paragraph(p))
        else:
            out.append(p)
    return out
