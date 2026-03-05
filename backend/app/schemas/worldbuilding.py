"""
世界观设定相关的 Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class WorldbuildingBase(BaseModel):
    """世界观设定基础字段"""
    category: str = Field(default="其他", max_length=50, description="分类")
    title: str = Field(..., max_length=200, description="标题")
    content: Optional[str] = Field(default=None, description="内容")
    trigger_keywords: Optional[str] = Field(default=None, description="触发关键词(JSON)")
    parent_id: Optional[int] = Field(default=None, description="父节点ID")
    level: int = Field(default=0, description="层级")
    sort_order: int = Field(default=0, description="排序")
    icon: Optional[str] = Field(default=None, description="图标")
    color: Optional[str] = Field(default=None, description="颜色")


class WorldbuildingCreate(WorldbuildingBase):
    """创建世界观设定"""
    pass


class WorldbuildingUpdate(BaseModel):
    """更新世界观设定 - 所有字段可选"""
    category: Optional[str] = None
    title: Optional[str] = None
    content: Optional[str] = None
    trigger_keywords: Optional[str] = None
    parent_id: Optional[int] = None
    level: Optional[int] = None
    sort_order: Optional[int] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class WorldbuildingResponse(WorldbuildingBase):
    """世界观设定响应"""
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorldbuildingTreeResponse(WorldbuildingResponse):
    """世界观设定树形响应（含子节点）"""
    children: List["WorldbuildingTreeResponse"] = []


class WorldbuildingListResponse(BaseModel):
    """世界观设定列表响应"""
    items: List[WorldbuildingResponse]
    total: int