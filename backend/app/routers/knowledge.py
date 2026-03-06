"""
知识库路由
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.knowledge import KnowledgeEntry
from app.schemas.knowledge import (
    KnowledgeEntryCreate,
    KnowledgeEntryResponse,
    KnowledgeSearchRequest,
)
from app.services.knowledge import knowledge_service


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.post("/search", response_model=List[KnowledgeEntryResponse])
async def search_and_learn(
    request: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db)
):
    """通过关键词搜索并学习知识"""
    all_entries = []
    for keyword in request.keywords:
        entries = await knowledge_service.search_and_store(
            db, keyword, request.max_results_per_keyword, request.use_ai
        )
        all_entries.extend(entries)

    return all_entries


@router.post("/", response_model=KnowledgeEntryResponse)
async def create_knowledge(
    payload: KnowledgeEntryCreate,
    db: AsyncSession = Depends(get_db)
):
    """手动创建知识条目"""
    entry = KnowledgeEntry(**payload.model_dump())
    entry.char_count = len(payload.content)
    entry.source_type = "manual"
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    # 向量化
    await knowledge_service._vectorize_knowledge(db, entry.id)

    return entry


@router.get("/", response_model=List[KnowledgeEntryResponse])
async def list_knowledge(
    keyword: str = None,
    db: AsyncSession = Depends(get_db)
):
    """获取所有知识条目"""
    query = select(KnowledgeEntry)
    if keyword:
        query = query.where(KnowledgeEntry.keyword.contains(keyword))

    result = await db.execute(query.order_by(KnowledgeEntry.created_at.desc()))
    return result.scalars().all()


@router.get("/{entry_id}", response_model=KnowledgeEntryResponse)
async def get_knowledge(
    entry_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取单个知识条目"""
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return entry


@router.delete("/{entry_id}", status_code=204)
async def delete_knowledge(
    entry_id: int,
    db: AsyncSession = Depends(get_db)
):
    """删除知识条目"""
    result = await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    await db.delete(entry)
    await db.commit()
