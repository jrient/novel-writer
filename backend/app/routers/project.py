"""
项目路由
处理小说项目的 CRUD 操作
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse, ProjectListResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("/", response_model=List[ProjectListResponse])
async def list_projects(
    status: Optional[str] = Query(None, description="按状态过滤: draft/in_progress/completed"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出当前用户的所有项目，支持按 status 过滤"""
    stmt = (
        select(Project)
        .where(Project.owner_id == current_user.id)
        .order_by(Project.created_at.desc())
    )
    if status:
        stmt = stmt.where(Project.status == status)
    result = await db.execute(stmt)
    projects = result.scalars().all()
    return projects


@router.post("/", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建新项目"""
    try:
        project = Project(**payload.model_dump(), owner_id=current_user.id)
        db.add(project)
        await db.commit()
        await db.refresh(project)
        # 刷新后加载关联章节（新建项目章节为空）
        await db.execute(
            select(Project).where(Project.id == project.id).options(selectinload(Project.chapters))
        )
        return project
    except Exception as e:
        await db.rollback()
        logger.error(f"创建项目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建项目失败")


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
):
    """获取项目详情，包含所有章节"""
    return project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """更新项目信息"""
    try:
        # 只更新有值的字段
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(project, key, value)

        await db.commit()
        await db.refresh(project)
        return project
    except Exception as e:
        await db.rollback()
        logger.error(f"更新项目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新项目失败")


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """删除项目（级联删除所有章节）"""
    try:
        await db.delete(project)
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.error(f"删除项目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除项目失败")