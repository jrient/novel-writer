"""
项目 Pydantic 模式
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    """创建项目时的请求体"""
    title: str
    description: Optional[str] = None
    genre: Optional[str] = None
    target_word_count: int = 0
    status: str = "draft"
    outline: Optional[str] = None


class ProjectUpdate(BaseModel):
    """更新项目时的请求体（所有字段可选）"""
    title: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    target_word_count: Optional[int] = None
    current_word_count: Optional[int] = None
    status: Optional[str] = None
    outline: Optional[str] = None


class ChapterSummary(BaseModel):
    """章节简要信息（嵌入在项目响应中）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    sort_order: int
    word_count: int
    status: str
    pov_character: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ProjectResponse(BaseModel):
    """项目详情响应（含章节列表）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    genre: Optional[str] = None
    target_word_count: int
    current_word_count: int
    status: str
    outline: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    chapters: List[ChapterSummary] = []


class ProjectListResponse(BaseModel):
    """项目列表响应（不含章节内容）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    genre: Optional[str] = None
    target_word_count: int
    current_word_count: int
    status: str
    outline: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
