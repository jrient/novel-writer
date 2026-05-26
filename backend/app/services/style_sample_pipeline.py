"""StyleSample 后台索引 + 抽取 pipeline 编排

包装 indexer + extractor，负责：
  - 把 index_status 推进到 indexing / ready / failed
  - 写 index_error
  - 写 extracted_at / extraction_model
  - 任何一步失败 → 整体 failed，chunks 全删（indexer 内自己处理）
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.style_sample import StyleSample
from app.services import style_sample_indexer, style_guide_extractor

logger = logging.getLogger(__name__)


async def run(session_factory: async_sessionmaker, sample_id: int) -> None:
    """对 sample 跑完整 pipeline：embedding + 抽取 → 落库。

    每个阶段开自己的 session（background task 路径，外层 HTTP session 已关）。
    任何阶段失败 → 标 failed + 写 error，并保证不留半成品。
    """
    # 阶段 1：标 indexing
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.index_status = "indexing"
        sample.index_error = None
        await session.commit()
        title = sample.title
        content = sample.content

    # 阶段 2：embedding
    try:
        async with session_factory() as session:
            await style_sample_indexer.index_sample(session, sample_id)
    except Exception as e:
        logger.exception("style_sample embedding 失败 sample_id=%s", sample_id)
        await _mark_failed(session_factory, sample_id, f"embedding 失败: {e}")
        return

    # 阶段 3：LLM 抽取
    try:
        guide_json, model_name = await style_guide_extractor.extract(title, content)
    except style_guide_extractor.StyleGuideExtractionError as e:
        logger.exception("style_sample 抽取失败 sample_id=%s", sample_id)
        async with session_factory() as session:
            await style_sample_indexer._delete_chunks_only(session, sample_id)
        await _mark_failed(session_factory, sample_id, f"抽取失败: {e}")
        return

    # 阶段 4：写抽取结果 + 标 ready
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.style_guide = guide_json
        sample.extraction_model = model_name
        sample.extracted_at = datetime.utcnow()
        sample.index_status = "ready"
        sample.index_error = None
        await session.commit()


async def _mark_failed(session_factory: async_sessionmaker, sample_id: int, error: str) -> None:
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.index_status = "failed"
        sample.index_error = error[:2000]
        await session.commit()
