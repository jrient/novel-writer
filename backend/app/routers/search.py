"""
语义搜索路由
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel

from app.core.database import get_db
from app.models.embedding import NovelChunk
from app.services.embedding import embedding_service


router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchResult(BaseModel):
    chunk_id: int
    reference_id: int
    content: str
    similarity: float
    chapter_title: Optional[str] = None


@router.get("/semantic", response_model=List[SearchResult])
async def semantic_search(
    query: str = Query(..., description="搜索查询"),
    limit: int = Query(10, ge=1, le=50, description="返回结果数量"),
    reference_id: Optional[int] = Query(None, description="限定参考小说ID"),
    db: AsyncSession = Depends(get_db)
):
    """语义搜索参考小说片段"""
    # 生成查询向量
    query_embedding = await embedding_service.generate_embedding(query)

    # 构建SQL查询
    sql = """
        SELECT
            id, reference_id, content, chapter_title,
            1 - (embedding <=> :query_embedding) as similarity
        FROM novel_chunks
        WHERE embedding IS NOT NULL
    """

    params = {"query_embedding": str(query_embedding)}

    if reference_id:
        sql += " AND reference_id = :reference_id"
        params["reference_id"] = reference_id

    sql += " ORDER BY embedding <=> :query_embedding LIMIT :limit"
    params["limit"] = limit

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        SearchResult(
            chunk_id=row[0],
            reference_id=row[1],
            content=row[2],
            chapter_title=row[3],
            similarity=float(row[4])
        )
        for row in rows
    ]
