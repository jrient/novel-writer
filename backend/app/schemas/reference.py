"""
参考小说相关 Pydantic Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field


class ReferenceNovelCreate(BaseModel):
    """创建参考小说"""
    title: str = Field(..., max_length=200)
    author: Optional[str] = Field(default=None, max_length=100)
    genre: Optional[str] = Field(default=None, max_length=50)
    source: Optional[str] = Field(default=None, max_length=200)
    tags: Optional[str] = Field(default=None, description="JSON 标签数组")
    reference_type: Optional[str] = Field(default="all", description="参考类型: style/structure/worldbuilding/character/dialogue/all")
    summary: Optional[str] = None
    notes: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)


class ReferenceNovelUpdate(BaseModel):
    """更新参考小说"""
    title: Optional[str] = None
    author: Optional[str] = None
    genre: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
    reference_type: Optional[str] = None
    summary: Optional[str] = None
    notes: Optional[str] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    writing_style: Optional[str] = None


class ReferenceNovelResponse(BaseModel):
    """参考小说响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: Optional[str] = None
    genre: Optional[str] = None
    source: Optional[str] = None
    tags: Optional[str] = None
    reference_type: Optional[str] = None
    file_path: Optional[str] = None
    file_format: Optional[str] = None
    total_chars: int = 0
    chapter_count: int = 0
    avg_chapter_length: int = 0
    summary: Optional[str] = None
    writing_style: Optional[str] = None
    rating: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ReferenceNovelDetailResponse(ReferenceNovelResponse):
    """参考小说详情响应（含分析数据）"""
    analysis: Optional[str] = None
    content: Optional[str] = None
    chapters_data: Optional[str] = None


class ReferenceStatsResponse(BaseModel):
    """参考库统计信息"""
    total_count: int
    genre_distribution: dict  # {"科幻": 3, "奇幻": 5}
    avg_length: int
    total_chars: int
    type_distribution: dict  # {"style": 2, "structure": 3}
