"""StyleSample / StyleSampleChunk 模型 schema 与 CASCADE 验证"""
import pytest
from sqlalchemy import select

from app.models.style_sample import StyleSample, StyleSampleChunk


@pytest.mark.asyncio
async def test_create_style_sample_minimal(db_session):
    s = StyleSample(title="测试样本", content="正文 1234")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    assert s.id is not None
    assert s.title == "测试样本"
    assert s.index_status == "pending"
    assert s.total_chars == 0


@pytest.mark.asyncio
async def test_create_style_sample_full(db_session):
    s = StyleSample(
        title="完整字段",
        author="作者甲",
        source="知乎严选",
        genre="都市言情",
        tags='["甜文", "高糖"]',
        notes="运营备注",
        file_path="uploads/style/x.txt",
        file_format="txt",
        content="原文" * 100,
        total_chars=200,
        style_guide='{"structured": {}, "prose_excerpt": "", "prompt_fragment": ""}',
        extraction_model="claude-sonnet-4",
        index_status="ready",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    assert s.genre == "都市言情"
    assert s.index_status == "ready"


@pytest.mark.asyncio
async def test_chunk_cascade_delete(db_session):
    s = StyleSample(title="将被删", content="x")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    c = StyleSampleChunk(
        sample_id=s.id, chunk_index=0, content="片段一", char_count=3
    )
    db_session.add(c)
    await db_session.commit()

    await db_session.delete(s)
    await db_session.commit()

    remaining = (await db_session.execute(select(StyleSampleChunk))).scalars().all()
    assert remaining == []
