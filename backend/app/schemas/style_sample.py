"""StyleSample API schemas

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第四节。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class StyleGuideStructured(BaseModel):
    pov: Optional[str] = None
    tense: Optional[str] = None
    sentence_length: Optional[str] = None
    dialogue_density: Optional[str] = None
    pacing: Optional[str] = None
    opening_formula: Optional[str] = None
    ending_formula: Optional[str] = None
    signature_devices: list[str] = Field(default_factory=list)


class StyleGuide(BaseModel):
    structured: StyleGuideStructured = Field(default_factory=StyleGuideStructured)
    prose_excerpt: str = ""
    prompt_fragment: str = ""


class StyleSampleSummary(BaseModel):
    """列表项 —— 不含 content / chunks"""
    id: int
    title: str
    author: Optional[str]
    source: Optional[str]
    genre: Optional[str]
    tags: Optional[str]
    total_chars: int
    index_status: str
    index_error: Optional[str]
    extracted_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class StyleSampleDetail(StyleSampleSummary):
    """详情 —— 含 content / 解析后的 style_guide / file 元信息"""
    file_path: Optional[str]
    file_format: Optional[str]
    notes: Optional[str]
    content: str
    style_guide: Optional[StyleGuide] = None
    extraction_model: Optional[str]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filter: dict[str, Any] = Field(default_factory=dict)


class SearchHitChunk(BaseModel):
    chunk_index: int
    content: str
    char_count: int
    similarity: float


class SearchHit(BaseModel):
    sample: StyleSampleSummary
    top_chunks: list[SearchHitChunk]
    style_guide: Optional[StyleGuide] = None
