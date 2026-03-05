"""
路由包初始化
"""
from app.routers.project import router as project_router
from app.routers.chapter import router as chapter_router

__all__ = ["project_router", "chapter_router"]
