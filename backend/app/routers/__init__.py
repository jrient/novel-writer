"""
路由包初始化
"""
from app.routers.project import router as project_router
from app.routers.chapter import router as chapter_router
from app.routers.character import router as character_router
from app.routers.worldbuilding import router as worldbuilding_router
from app.routers.outline import router as outline_router

__all__ = [
    "project_router",
    "chapter_router",
    "character_router",
    "worldbuilding_router",
    "outline_router",
]