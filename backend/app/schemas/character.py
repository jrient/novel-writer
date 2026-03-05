"""
角色相关的 Pydantic schemas
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class CharacterBase(BaseModel):
    """角色基础字段"""
    name: str = Field(..., max_length=100, description="角色名称")
    role_type: Optional[str] = Field(default="supporting", description="角色类型")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    age: Optional[str] = Field(default=None, description="年龄")
    gender: Optional[str] = Field(default=None, description="性别")
    occupation: Optional[str] = Field(default=None, description="职业")
    personality_traits: Optional[str] = Field(default=None, description="性格特征(JSON)")
    appearance: Optional[str] = Field(default=None, description="外貌描写")
    background: Optional[str] = Field(default=None, description="背景故事")
    relationships: Optional[str] = Field(default=None, description="角色关系(JSON)")
    growth_arc: Optional[str] = Field(default=None, description="成长弧线")
    tags: Optional[str] = Field(default=None, description="标签(JSON)")
    notes: Optional[str] = Field(default=None, description="备注")


class CharacterCreate(CharacterBase):
    """创建角色"""
    pass


class CharacterUpdate(BaseModel):
    """更新角色 - 所有字段可选"""
    name: Optional[str] = Field(default=None, max_length=100)
    role_type: Optional[str] = None
    avatar_url: Optional[str] = None
    age: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    personality_traits: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None
    relationships: Optional[str] = None
    growth_arc: Optional[str] = None
    tags: Optional[str] = None
    notes: Optional[str] = None


class CharacterResponse(CharacterBase):
    """角色响应"""
    id: int
    project_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CharacterListResponse(BaseModel):
    """角色列表响应"""
    items: List[CharacterResponse]
    total: int