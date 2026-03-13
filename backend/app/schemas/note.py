"""
笔记 Pydantic 模式
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict


class NoteBase(BaseModel):
    """笔记基础字段"""
    title: str
    content: Optional[str] = None
    note_type: str = "note"
    status: str = "active"


class NoteCreate(NoteBase):
    """创建笔记"""
    pass


class NoteUpdate(BaseModel):
    """更新笔记"""
    title: Optional[str] = None
    content: Optional[str] = None
    note_type: Optional[str] = None
    status: Optional[str] = None


class NoteResponse(NoteBase):
    """笔记响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    related_chapter_ids: Optional[List[int]] = None
    sort_order: int
    created_at: datetime
    updated_at: Optional[datetime] = None


class MiaojiParseRequest(BaseModel):
    """妙记解析请求"""
    content: str


class MiaojiParseResult(BaseModel):
    """妙记解析结果"""
    characters: List[dict] = []
    worldbuilding: List[dict] = []
    outline: List[dict] = []
    events: List[dict] = []
    summary: str = ""