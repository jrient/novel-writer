"""
知识库服务
通过Web搜索获取和管理知识
"""
import os
import httpx
import logging
from typing import List, Dict, Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)


def _get_proxy() -> Optional[str]:
    """从环境变量获取代理配置"""
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.knowledge import KnowledgeEntry
from app.models.embedding import NovelChunk
from app.services.embedding import embedding_service
from app.core.config import settings


class KnowledgeService:
    @staticmethod
    async def search_and_store(
        db: AsyncSession,
        keyword: str,
        max_results: int = 3,
        use_ai: bool = False
    ) -> List[KnowledgeEntry]:
        """通过Web搜索获取知识并存储"""
        # 选择搜索方式
        if use_ai and settings.OPENAI_API_KEY:
            from app.services.ai_search import AISearchService
            ai_search = AISearchService(
                settings.OPENAI_API_KEY,
                settings.OPENAI_BASE_URL,
                settings.JINA_API_KEY,
                settings.GEMINI_API_KEY
            )
            search_results = await ai_search.search(keyword, max_results)
            # AI搜索失败时回退到传统搜索
            if not search_results:
                logger.info(f"AI搜索无结果，回退到传统搜索: {keyword}")
                search_results = await KnowledgeService._web_search(keyword, max_results)
        else:
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
        """通过 Wikipedia + DuckDuckGo 进行真实 Web 搜索"""
        results: List[Dict] = []
        seen_titles: set = set()
        timeout = httpx.Timeout(10.0)
        proxy = _get_proxy()

        async with httpx.AsyncClient(timeout=timeout, proxy=proxy) as client:
            # 1. Wikipedia 中文搜索
            try:
                url = f"https://zh.wikipedia.org/api/rest_v1/page/summary/{quote(keyword)}"
                logger.info(f"Searching Wikipedia ZH: {url}")
                resp = await client.get(
                    url,
                    headers={"Accept": "application/json", "User-Agent": "NovelWriter/1.0"},
                    follow_redirects=True,
                )
                logger.info(f"Wikipedia ZH response: {resp.status_code}")
                if resp.status_code == 200:
                    data = resp.json()
                    title = data.get("title", "")
                    extract = data.get("extract", "")
                    if extract and title:
                        seen_titles.add(title.lower())
                        results.append({
                            "title": title,
                            "content": extract,
                            "url": data.get("content_urls", {}).get("desktop", {}).get("page", f"https://zh.wikipedia.org/wiki/{quote(keyword)}"),
                        })
            except Exception as e:
                logger.warning("Wikipedia 中文搜索失败: %s", e, exc_info=True)

            # 2. Wikipedia 英文回退
            if len(results) < max_results:
                try:
                    resp = await client.get(
                        f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(keyword)}",
                        headers={"Accept": "application/json", "User-Agent": "NovelWriter/1.0"},
                        follow_redirects=True,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get("title", "")
                        extract = data.get("extract", "")
                        if extract and title and title.lower() not in seen_titles:
                            seen_titles.add(title.lower())
                            results.append({
                                "title": title,
                                "content": extract,
                                "url": data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{quote(keyword)}"),
                            })
                except Exception as e:
                    logger.warning("Wikipedia 英文搜索失败: %s", e)

            # 3. DuckDuckGo Instant Answer API 补充
            if len(results) < max_results:
                try:
                    resp = await client.get(
                        "https://api.duckduckgo.com/",
                        params={"q": keyword, "format": "json", "no_html": "1"},
                        headers={"User-Agent": "NovelWriter/1.0"},
                        follow_redirects=True,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        # 提取 Abstract
                        abstract = data.get("Abstract", "")
                        abstract_url = data.get("AbstractURL", "")
                        abstract_source = data.get("AbstractSource", "")
                        if abstract and abstract_source.lower() not in seen_titles:
                            seen_titles.add(abstract_source.lower())
                            results.append({
                                "title": f"{keyword} - {abstract_source}",
                                "content": abstract,
                                "url": abstract_url or f"https://duckduckgo.com/?q={quote(keyword)}",
                            })

                        # 提取 RelatedTopics
                        for topic in data.get("RelatedTopics", []):
                            if len(results) >= max_results:
                                break
                            text = topic.get("Text", "")
                            first_url = topic.get("FirstURL", "")
                            if text and first_url:
                                topic_title = text[:50].split(" - ")[0] if " - " in text[:50] else text[:50]
                                if topic_title.lower() not in seen_titles:
                                    seen_titles.add(topic_title.lower())
                                    results.append({
                                        "title": topic_title,
                                        "content": text,
                                        "url": first_url,
                                    })
                except Exception as e:
                    logger.warning("DuckDuckGo 搜索失败: %s", e)

        return results[:max_results]

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
