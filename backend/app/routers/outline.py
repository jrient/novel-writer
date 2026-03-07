"""
大纲节点管理路由
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.outline import OutlineNode
from app.models.project import Project
from app.schemas.outline import (
    OutlineNodeCreate,
    OutlineNodeUpdate,
    OutlineNodeResponse,
    OutlineTreeResponse,
    OutlineNodeListResponse,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}/outline", tags=["outline"])


def build_outline_tree(nodes: List[OutlineNode]) -> List[OutlineTreeResponse]:
    """将扁平列表构建为树形结构"""
    node_map = {}
    for node in nodes:
        node_map[node.id] = OutlineTreeResponse(
            **{c.name: getattr(node, c.name) for c in node.__table__.columns},
            children=[]
        )

    roots = []
    for node in nodes:
        tree_node = node_map[node.id]
        if node.parent_id is None:
            roots.append(tree_node)
        else:
            parent = node_map.get(node.parent_id)
            if parent:
                parent.children.append(tree_node)

    return roots


@router.get("/", response_model=List[OutlineNodeResponse])
async def get_outline_nodes(
    project_id: int,
    node_type: str = None,
    db: AsyncSession = Depends(get_db),
):
    """获取项目的大纲节点（扁平列表）"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="项目不存在")

    query = select(OutlineNode).where(OutlineNode.project_id == project_id)
    if node_type:
        query = query.where(OutlineNode.node_type == node_type)
    query = query.order_by(OutlineNode.sort_order)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/tree", response_model=List[OutlineTreeResponse])
async def get_outline_tree(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取大纲树形结构"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="项目不存在")

    query = select(OutlineNode).where(
        OutlineNode.project_id == project_id
    ).order_by(OutlineNode.sort_order)

    result = await db.execute(query)
    nodes = result.scalars().all()

    return build_outline_tree(nodes)


@router.post("/", response_model=OutlineNodeResponse)
async def create_outline_node(
    project_id: int,
    data: OutlineNodeCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建大纲节点"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="项目不存在")

    node = OutlineNode(project_id=project_id, **data.model_dump())
    db.add(node)
    await db.commit()
    await db.refresh(node)

    return node


@router.get("/{node_id}", response_model=OutlineNodeResponse)
async def get_outline_node(
    project_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取单个大纲节点"""
    result = await db.execute(
        select(OutlineNode).where(
            OutlineNode.id == node_id,
            OutlineNode.project_id == project_id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="大纲节点不存在")

    return node


@router.put("/{node_id}", response_model=OutlineNodeResponse)
async def update_outline_node(
    project_id: int,
    node_id: int,
    data: OutlineNodeUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新大纲节点"""
    result = await db.execute(
        select(OutlineNode).where(
            OutlineNode.id == node_id,
            OutlineNode.project_id == project_id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="大纲节点不存在")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(node, field, value)

    await db.commit()
    await db.refresh(node)

    return node


@router.delete("/{node_id}")
async def delete_outline_node(
    project_id: int,
    node_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除大纲节点"""
    result = await db.execute(
        select(OutlineNode).where(
            OutlineNode.id == node_id,
            OutlineNode.project_id == project_id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="大纲节点不存在")

    await db.delete(node)
    await db.commit()

    return {"message": "大纲节点已删除"}


@router.post("/reorder")
async def reorder_outline_nodes(
    project_id: int,
    orders: List[dict],
    db: AsyncSession = Depends(get_db),
):
    """批量更新大纲节点排序"""
    for item in orders:
        node_id = item.get("id")
        sort_order = item.get("sort_order")
        parent_id = item.get("parent_id")

        result = await db.execute(
            select(OutlineNode).where(
                OutlineNode.id == node_id,
                OutlineNode.project_id == project_id,
            )
        )
        node = result.scalar_one_or_none()
        if node:
            node.sort_order = sort_order
            if parent_id is not None:
                node.parent_id = parent_id

    await db.commit()
    return {"message": "排序已更新"}