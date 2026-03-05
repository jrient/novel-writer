"""
大纲节点相关的 Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class OutlineNodeBase(BaseModel):
    """大纲节点基础字段"""
    node_type: str = Field(default="chapter", description="节点类型")
    title: str = Field(..., max_length=200, description="标题")
    content: Optional[str] = Field(default=None, description="内容/描述")
    parent_id: Optional[int] = Field(default=None, description="父节点ID")
    level: int = Field(default=0, description="层级")
    sort_order: int = Field(default=0, description="排序")
    chapter_id: Optional[int] = Field(default=None, description="关联章节ID")
    pov_character_id: Optional[int] = Field(default=None, description="POV角色ID")
    status: str = Field(default="planning", description="状态")
    estimated_words: Optional[int] = Field(default=None, description="预估字数")
    notes: Optional[str] = Field(default=None, description="备注")


class OutlineNodeCreate(OutlineNodeBase):
    """创建大纲节点"""
    pass


class OutlineNodeUpdate(BaseModel):
    """更新大纲节点 - 所有字段可选"""
    node_type: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    parent_id: Optional[int] = None
    level: Optional[int] = None
    sort_order: Optional[int] = None
    chapter_id: Optional[int] = None
    pov_character_id: Optional[int] = None
    status: Optional[str] = None
    estimated_words: Optional[int] = None
    notes: Optional[str] = None


class OutlineNodeResponse(OutlineNodeBase):
    """大纲节点响应"""
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OutlineTreeResponse(OutlineNodeResponse):
    """大纲树形响应（含子节点）"""
    children: List["OutlineTreeResponse"] = []


class OutlineNodeListResponse(BaseModel):
    """大纲节点列表响应"""
    items: List[OutlineNodeResponse]
    total: int