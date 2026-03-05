"""
模型包初始化
导入所有模型，确保 Base.metadata 包含所有表定义
"""
from app.models.project import Project
from app.models.chapter import Chapter

__all__ = ["Project", "Chapter"]
