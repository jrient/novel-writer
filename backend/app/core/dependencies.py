"""
共享依赖函数
提供可复用的路由依赖项
"""
from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.project import Project


async def get_project_or_404(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """
    获取项目，不存在则抛出 404
    可作为 FastAPI 依赖项使用
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project