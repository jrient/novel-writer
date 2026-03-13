"""
向导模块 Pydantic 模式
用于创作向导的请求和响应定义
支持新的地图->部分->章节层级结构
"""
from __future__ import annotations
from typing import List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, field_validator


def generate_uuid() -> str:
    """生成 UUID"""
    return str(uuid.uuid4())[:8]


def coerce_id(v: Union[str, int, None]) -> Optional[str]:
    """将 ID 转换为字符串（兼容前端发送整数的情况）"""
    if v is None:
        return None
    return str(v)


# ============ 新的数据结构 ============

class SceneNode(BaseModel):
    """场景节点"""
    id: Optional[str] = None
    name: str
    description: Optional[str] = None

    _validate_id = field_validator('id', mode='before')(coerce_id)


class ChapterOutlineItem(BaseModel):
    """章节大纲项"""
    id: Optional[str] = None
    chapter: int
    title: str
    summary: str
    scenes: Optional[List[SceneNode]] = None

    _validate_id = field_validator('id', mode='before')(coerce_id)


class PartNode(BaseModel):
    """部分节点"""
    id: Optional[str] = None
    name: str  # 第一部分、第二部分
    summary: Optional[str] = None
    chapters: List[ChapterOutlineItem] = []
    character_ids: List[str] = []  # 出场角色ID

    _validate_id = field_validator('id', mode='before')(coerce_id)


class MapNode(BaseModel):
    """地图节点"""
    id: Optional[str] = None
    name: str  # 青云宗、北境荒漠
    description: Optional[str] = None
    parts: List[PartNode] = []

    _validate_id = field_validator('id', mode='before')(coerce_id)


class CharacterOutlineItem(BaseModel):
    """角色大纲项"""
    id: Optional[str] = None
    name: str
    role_type: str = "supporting"  # protagonist/antagonist/supporting/minor
    gender: Optional[str] = None
    age: Optional[str] = None
    occupation: Optional[str] = None
    personality_traits: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None
    appearances: List[str] = []  # 出场章节ID列表
    origin_map_id: Optional[str] = None  # 初次登场的地图ID

    _validate_id = field_validator('id', 'origin_map_id', mode='before')(coerce_id)


class NoteItem(BaseModel):
    """笔记项"""
    id: Optional[str] = None
    note_type: str = "note"  # foreshadowing/inspiration/note
    title: str
    content: Optional[str] = None
    related_chapter_ids: List[str] = []
    target_type: Optional[str] = None  # map/part/chapter 关联目标类型
    target_id: Optional[str] = None  # 关联目标ID
    status: str = "active"  # active/resolved/abandoned

    _validate_id = field_validator('id', 'target_id', mode='before')(coerce_id)


# ============ 新的向导请求/响应 ============

class WizardIdeaRequest(BaseModel):
    """步骤1：创作思路请求（简化版）"""
    title: str
    genre: Optional[str] = None
    description: str
    reference_ids: Optional[List[int]] = None


class WizardMapsRequest(BaseModel):
    """步骤2：生成地图请求"""
    title: str
    genre: Optional[str] = None
    description: str
    reference_ids: Optional[List[int]] = None
    # 修改意见
    revision_request: Optional[str] = None
    current_maps: Optional[List[MapNode]] = None


class WizardPartsRequest(BaseModel):
    """步骤3：生成部分请求"""
    title: str
    genre: Optional[str] = None
    description: str
    map_id: str  # 选中的地图ID
    map_name: str  # 地图名称
    # 修改意见
    revision_request: Optional[str] = None
    current_parts: Optional[List[PartNode]] = None


class WizardCharactersForPartRequest(BaseModel):
    """步骤4：为部分生成角色请求"""
    title: str
    genre: Optional[str] = None
    description: str
    parts: List[PartNode]  # 已确认的部分
    existing_characters: Optional[List[CharacterOutlineItem]] = None  # 已有角色库


class WizardCreateV2Request(BaseModel):
    """向导创建项目请求（新版本）"""
    title: str
    genre: Optional[str] = None
    description: Optional[str] = None
    maps: List[MapNode]  # 地图结构
    characters: List[CharacterOutlineItem]  # 角色库
    notes: Optional[List[NoteItem]] = None  # 笔记（可选）
    reference_ids: Optional[List[int]] = None


# ============ 保留旧接口兼容 ============

class WizardGenerateRequest(BaseModel):
    """向导生成请求：生成大纲和角色（保留兼容性）"""
    title: str
    genre: Optional[str] = None
    description: str
    target_word_count: int = 100000
    chapter_count: int = 10
    reference_ids: Optional[List[int]] = None
    revision_request: Optional[str] = None
    current_outline: Optional[List[ChapterOutlineItem]] = None
    current_characters: Optional[List[CharacterOutlineItem]] = None


class WizardOutlineRequest(BaseModel):
    """向导生成大纲请求（保留兼容性）"""
    title: str
    genre: Optional[str] = None
    description: str
    target_word_count: int = 100000
    chapter_count: int = 10
    reference_ids: Optional[List[int]] = None
    revision_request: Optional[str] = None
    current_outline: Optional[List[ChapterOutlineItem]] = None


class WizardCharactersRequest(BaseModel):
    """向导生成角色请求（保留兼容性）"""
    title: str
    genre: Optional[str] = None
    description: str
    outline: List[ChapterOutlineItem]


class WizardCreateRequest(BaseModel):
    """向导创建项目请求（保留兼容性）"""
    title: str
    genre: Optional[str] = None
    description: Optional[str] = None
    target_word_count: int = 100000
    outline: List[ChapterOutlineItem]
    characters: List[CharacterOutlineItem]
    reference_ids: Optional[List[int]] = None
    outline_text: Optional[str] = None


class WizardCreateResponse(BaseModel):
    """向导创建项目响应"""
    project_id: int
    message: str