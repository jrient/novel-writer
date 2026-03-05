"""
Schemas 包初始化
"""
from app.schemas.project import (
    ProjectCreate,
    ProjectUpdate,
    ProjectResponse,
    ProjectListResponse,
)
from app.schemas.chapter import (
    ChapterCreate,
    ChapterUpdate,
    ChapterResponse,
)
from app.schemas.character import (
    CharacterCreate,
    CharacterUpdate,
    CharacterResponse,
    CharacterListResponse,
)
from app.schemas.worldbuilding import (
    WorldbuildingCreate,
    WorldbuildingUpdate,
    WorldbuildingResponse,
    WorldbuildingTreeResponse,
    WorldbuildingListResponse,
)
from app.schemas.outline import (
    OutlineNodeCreate,
    OutlineNodeUpdate,
    OutlineNodeResponse,
    OutlineTreeResponse,
    OutlineNodeListResponse,
)

__all__ = [
    # Project
    "ProjectCreate",
    "ProjectUpdate",
    "ProjectResponse",
    "ProjectListResponse",
    # Chapter
    "ChapterCreate",
    "ChapterUpdate",
    "ChapterResponse",
    # Character
    "CharacterCreate",
    "CharacterUpdate",
    "CharacterResponse",
    "CharacterListResponse",
    # Worldbuilding
    "WorldbuildingCreate",
    "WorldbuildingUpdate",
    "WorldbuildingResponse",
    "WorldbuildingTreeResponse",
    "WorldbuildingListResponse",
    # Outline
    "OutlineNodeCreate",
    "OutlineNodeUpdate",
    "OutlineNodeResponse",
    "OutlineTreeResponse",
    "OutlineNodeListResponse",
]