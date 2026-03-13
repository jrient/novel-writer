"""
世界观设定管理路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.worldbuilding import WorldbuildingEntry
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.worldbuilding import (
    WorldbuildingCreate,
    WorldbuildingUpdate,
    WorldbuildingResponse,
    WorldbuildingTreeResponse,
    WorldbuildingListResponse,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/worldbuilding", tags=["worldbuilding"])


def build_tree(entries: List[WorldbuildingEntry]) -> List[WorldbuildingTreeResponse]:
    """将扁平列表构建为树形结构"""
    # 创建 ID 到节点的映射
    node_map = {}
    for entry in entries:
        node_map[entry.id] = WorldbuildingTreeResponse(
            **{c.name: getattr(entry, c.name) for c in entry.__table__.columns},
            children=[]
        )

    # 构建树
    roots = []
    for entry in entries:
        node = node_map[entry.id]
        if entry.parent_id is None:
            roots.append(node)
        else:
            parent = node_map.get(entry.parent_id)
            if parent:
                parent.children.append(node)

    return roots


@router.get("/", response_model=List[WorldbuildingResponse])
async def get_worldbuilding(
    project_id: int,
    category: str = None,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取项目的世界观设定（扁平列表）"""
    query = select(WorldbuildingEntry).where(WorldbuildingEntry.project_id == project_id)
    if category:
        query = query.where(WorldbuildingEntry.category == category)
    query = query.order_by(WorldbuildingEntry.sort_order)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tree", response_model=List[WorldbuildingTreeResponse])
async def get_worldbuilding_tree(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取世界观设定树形结构"""
    query = select(WorldbuildingEntry).where(
        WorldbuildingEntry.project_id == project_id
    ).order_by(WorldbuildingEntry.sort_order)

    result = await db.execute(query)
    entries = result.scalars().all()

    return build_tree(entries)


@router.post("/", response_model=WorldbuildingResponse)
async def create_worldbuilding(
    project_id: int,
    data: WorldbuildingCreate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """创建世界观设定"""
    entry = WorldbuildingEntry(project_id=project_id, **data.model_dump())
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return entry


@router.get("/{entry_id}", response_model=WorldbuildingResponse)
async def get_worldbuilding_entry(
    project_id: int,
    entry_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取单个世界观设定"""
    result = await db.execute(
        select(WorldbuildingEntry).where(
            WorldbuildingEntry.id == entry_id,
            WorldbuildingEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="设定不存在")

    return entry


@router.put("/{entry_id}", response_model=WorldbuildingResponse)
async def update_worldbuilding(
    project_id: int,
    entry_id: int,
    data: WorldbuildingUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """更新世界观设定"""
    result = await db.execute(
        select(WorldbuildingEntry).where(
            WorldbuildingEntry.id == entry_id,
            WorldbuildingEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="设定不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    await db.commit()
    await db.refresh(entry)

    return entry


@router.delete("/{entry_id}")
async def delete_worldbuilding(
    project_id: int,
    entry_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """删除世界观设定"""
    result = await db.execute(
        select(WorldbuildingEntry).where(
            WorldbuildingEntry.id == entry_id,
            WorldbuildingEntry.project_id == project_id,
        )
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="设定不存在")

    await db.delete(entry)
    await db.commit()

    return {"message": "设定已删除"}