"""
知识库服务
通过Web搜索获取和管理知识
"""
import httpx
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.knowledge import KnowledgeEntry
from app.models.embedding import NovelChunk
from app.services.embedding import embedding_service


class KnowledgeService:
    @staticmethod
    async def search_and_store(
        db: AsyncSession,
        keyword: str,
        max_results: int = 3
    ) -> List[KnowledgeEntry]:
        """通过Web搜索获取知识并存储"""
        # 使用简单的HTTP搜索（实际应该集成专业搜索API）
        search_results = await KnowledgeService._web_search(keyword, max_results)

        entries = []
        for result in search_results:
            # 创建知识条目
            entry = KnowledgeEntry(
                keyword=keyword,
                title=result["title"],
                content=result["content"],
                source_url=result.get("url"),
                source_type="web_search",
                char_count=len(result["content"])
            )
            db.add(entry)
            entries.append(entry)

        await db.commit()

        # 向量化知识内容
        for entry in entries:
            await KnowledgeService._vectorize_knowledge(db, entry.id)

        return entries

    @staticmethod
    async def _web_search(keyword: str, max_results: int) -> List[Dict]:
        """Web搜索（简化版）"""
        # TODO: 集成真实的搜索API（如Google Search API, Bing API等）
        # 这里返回模拟数据
        return [
            {
                "title": f"{keyword}相关知识 - 条目1",
                "content": f"关于{keyword}的详细介绍...",
                "url": f"https://example.com/{keyword}/1"
            }
        ]

    @staticmethod
    async def _vectorize_knowledge(db: AsyncSession, knowledge_id: int):
        """将知识条目向量化"""
        result = await db.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.id == knowledge_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            return

        # 生成embedding
        embedding = await embedding_service.generate_embedding(entry.content)

        # 存储为chunk（复用现有的向量存储）
        chunk = NovelChunk(
            reference_id=-knowledge_id,  # 负数表示知识条目
            chunk_index=0,
            content=entry.content,
            char_count=entry.char_count,
            embedding=embedding,
            chapter_title=entry.title
        )
        db.add(chunk)
        await db.commit()


knowledge_service = KnowledgeService()
