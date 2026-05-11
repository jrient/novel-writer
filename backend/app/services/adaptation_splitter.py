"""按场切分剧本文本。

正则优先：命中 ≥2 处场标记则用正则；否则返回空列表，调用方走 LLM fallback。
不在此模块直接调用 LLM，便于单测。
"""
import re
from dataclasses import dataclass
from typing import List

_PATTERNS = [
    re.compile(r"^\s*场\s*\d+", re.MULTILINE),
    re.compile(r"^\s*第[一二三四五六七八九十百千\d]+场", re.MULTILINE),
    re.compile(r"^\s*INT\.|^\s*EXT\.", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s*[内外]景", re.MULTILINE),
]

_LOOSE_PATTERNS = [
    re.compile(r"^\s*\d{1,3}\s*$", re.MULTILINE),
]
_LOOSE_MIN_MATCHES = 3


@dataclass
class SceneBoundary:
    index: int
    start: int
    end: int
    title: str


def _collect_match_starts(text: str) -> list[int]:
    starts: set[int] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            starts.add(m.start())
    if len(starts) < 2:
        loose: set[int] = set()
        for pat in _LOOSE_PATTERNS:
            for m in pat.finditer(text):
                loose.add(m.start())
        if len(loose) >= _LOOSE_MIN_MATCHES:
            starts = loose
    return sorted(starts)


def _title_at(text: str, start: int) -> str:
    end_of_line = text.find("\n", start)
    if end_of_line == -1:
        end_of_line = len(text)
    return text[start:end_of_line].strip()[:80]


def split_by_regex(text: str) -> List[SceneBoundary]:
    """按正则切场。命中 <2 返回空列表。"""
    starts = _collect_match_starts(text)
    if len(starts) < 2:
        return []
    boundaries: list[SceneBoundary] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        boundaries.append(
            SceneBoundary(index=i, start=s, end=e, title=_title_at(text, s))
        )
    return boundaries
