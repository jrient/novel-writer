"""
共享依赖函数
提供可复用的路由依赖项
"""
from typing import Optional

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user


async def get_project_or_404(
    project_id: int,
    db: AsyncSession = Depends(get_db),
) -> Project:
    """
    获取项目，不存在则抛出 404
    可作为 FastAPI 依赖项使用（无认证）
    """
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def get_project_with_auth(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Project:
    """
    获取项目（带用户认证和数据隔离）
    确保用户只能访问自己的项目
    """
    result = await db.execute(
        select(Project)
        .where(
            Project.id == project_id,
            Project.owner_id == current_user.id,
        )
        .options(selectinload(Project.chapters))
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    return project


async def get_optional_current_user(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
) -> Optional[User]:
    """获取可选的当前用户（不强制要求登录）"""
    return current_user