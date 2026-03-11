"""
向导模块 Pydantic 模式
用于创作向导的请求和响应定义
"""
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class WizardGenerateRequest(BaseModel):
    """向导生成请求：生成大纲和角色"""
    title: str
    genre: Optional[str] = None
    description: str
    target_word_count: int = 100000
    chapter_count: int = 10
    reference_ids: Optional[List[int]] = None  # 参考小说 ID，用于风格参考


class ChapterOutlineItem(BaseModel):
    """章节大纲项"""
    chapter: int
    title: str
    summary: str


class CharacterOutlineItem(BaseModel):
    """角色大纲项"""
    name: str
    role_type: str = "supporting"  # protagonist/antagonist/supporting/minor
    gender: Optional[str] = None
    age: Optional[str] = None
    occupation: Optional[str] = None
    personality_traits: Optional[str] = None
    appearance: Optional[str] = None
    background: Optional[str] = None


class WizardCreateRequest(BaseModel):
    """向导创建项目请求"""
    title: str
    genre: Optional[str] = None
    description: Optional[str] = None
    target_word_count: int = 100000
    outline: List[ChapterOutlineItem]
    characters: List[CharacterOutlineItem]
    reference_ids: Optional[List[int]] = None


class WizardCreateResponse(BaseModel):
    """向导创建项目响应"""
    project_id: int
    message: str