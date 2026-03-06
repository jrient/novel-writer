"""
知识库Schema
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class KnowledgeEntryCreate(BaseModel):
    keyword: str
    title: str
    content: str
    source_url: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[str] = None


class KnowledgeEntryResponse(BaseModel):
    id: int
    keyword: str
    title: str
    content: str
    source_url: Optional[str] = None
    source_type: str
    category: Optional[str] = None
    tags: Optional[str] = None
    char_count: int
    usage_count: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class KnowledgeSearchRequest(BaseModel):
    keywords: List[str]
    max_results_per_keyword: int = 3
    use_ai: bool = False  # 是否使用AI增强搜索
