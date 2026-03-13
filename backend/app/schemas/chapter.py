"""
章节 Pydantic 模式
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class ChapterCreate(BaseModel):
    """创建章节时的请求体"""
    title: str
    content: str = ""
    summary: Optional[str] = None
    sort_order: Optional[int] = None  # 不传则自动追加到末尾
    status: str = "draft"
    pov_character: Optional[str] = None


class ChapterUpdate(BaseModel):
    """更新章节时的请求体（所有字段均为 Optional）"""
    title: Optional[str] = None
    content: Optional[str] = None
    summary: Optional[str] = None
    sort_order: Optional[int] = None
    status: Optional[str] = None
    pov_character: Optional[str] = None


class ChapterResponse(BaseModel):
    """章节详情响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    content: str
    summary: Optional[str] = None
    sort_order: int
    word_count: int
    status: str
    pov_character: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChapterBatchDeleteRequest(BaseModel):
    """批量删除请求体"""
    ids: list[int]


class ChapterReorderItem(BaseModel):
    """批量重排序时单条记录"""
    id: int
    sort_order: int


class ChapterReorderRequest(BaseModel):
    """批量重排序请求体"""
    orders: list[ChapterReorderItem]


# ========== 章节版本历史相关 ==========

class ChapterVersionResponse(BaseModel):
    """章节版本响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    version_number: int
    title: str
    word_count: int
    change_summary: Optional[str] = None
    created_at: datetime


class ChapterVersionDetail(BaseModel):
    """章节版本详情（包含内容）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    version_number: int
    title: str
    content: str
    word_count: int
    change_summary: Optional[str] = None
    created_at: datetime


class ChapterVersionRestore(BaseModel):
    """版本恢复响应"""
    message: str
    chapter: "ChapterResponse"
