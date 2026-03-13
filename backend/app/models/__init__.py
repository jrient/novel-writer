"""
模型包初始化
导入所有模型，确保 Base.metadata 包含所有表定义
"""
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.models.outline import OutlineNode
from app.models.reference import ReferenceNovel
from app.models.embedding import NovelChunk
from app.models.knowledge import KnowledgeEntry

from app.models.note import Note
from app.models.event import StoryEvent, Plotline

__all__ = ["Project", "Chapter", "ChapterVersion", "Character", "WorldbuildingEntry", "OutlineNode", "ReferenceNovel", "NovelChunk", "KnowledgeEntry", "Note", "StoryEvent", "Plotline"]