"""
角色管理路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.character import Character
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.character import (
    CharacterCreate,
    CharacterUpdate,
    CharacterResponse,
    CharacterListResponse,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/characters", tags=["characters"])


@router.get("/", response_model=List[CharacterResponse])
async def get_characters(
    project_id: int,
    role_type: Optional[str] = None,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
) -> List[CharacterResponse]:
    """获取项目的所有角色"""
    # 构建查询
    query = select(Character).where(Character.project_id == project_id)
    if role_type:
        query = query.where(Character.role_type == role_type)
    query = query.order_by(Character.id)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=CharacterResponse, status_code=201)
async def create_character(
    project_id: int,
    data: CharacterCreate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """创建角色"""
    character = Character(project_id=project_id, **data.model_dump())
    db.add(character)
    await db.commit()
    await db.refresh(character)

    return character


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    project_id: int,
    character_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """获取单个角色详情"""
    result = await db.execute(
        select(Character).where(
            Character.id == character_id,
            Character.project_id == project_id,
        )
    )
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail=f"角色不存在 (ID: {character_id})")

    return character


@router.put("/{character_id}", response_model=CharacterResponse)
async def update_character(
    project_id: int,
    character_id: int,
    data: CharacterUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
) -> CharacterResponse:
    """更新角色"""
    result = await db.execute(
        select(Character).where(
            Character.id == character_id,
            Character.project_id == project_id,
        )
    )
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail=f"角色不存在 (ID: {character_id})")

    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)

    await db.commit()
    await db.refresh(character)

    return character


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    project_id: int,
    character_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    """删除角色"""
    result = await db.execute(
        select(Character).where(
            Character.id == character_id,
            Character.project_id == project_id,
        )
    )
    character = result.scalar_one_or_none()
    if not character:
        raise HTTPException(status_code=404, detail=f"角色不存在 (ID: {character_id})")

    await db.delete(character)
    await db.commit()