"""
模型包初始化
导入所有模型，确保 Base.metadata 包含所有表定义
"""
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.outline import OutlineNode
from app.models.reference import ReferenceNovel

__all__ = ["Project", "Chapter", "Character", "WorldbuildingEntry", "OutlineNode", "ReferenceNovel"]