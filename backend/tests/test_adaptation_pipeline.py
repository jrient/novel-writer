"""改编流水线编排测试（mock LLMService）。"""
import asyncio
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock

from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.user import User
from app.services.adaptation_pipeline import AdaptationPipeline
from app.services.adaptation_splitter import SceneBoundary


@pytest.fixture
async def test_user(db_session):
    user = User(username="pipe_tester", email="pipe@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def fake_llm():
    svc = AsyncMock()
    svc.extract_entities = AsyncMock(return_value={
        "entities": [{"type": "person", "text": "李铁柱", "count": 3, "sample_context": "x"}],
        "character_traits": [{"name": "李铁柱", "tags": ["重情义"]}],
    })
    svc.split_by_llm = AsyncMock(return_value=[
        SceneBoundary(index=0, start=0, end=10, title="A"),
        SceneBoundary(index=1, start=10, end=20, title="B"),
    ])

    async def fake_rewrite(**kw):
        return "改:" + kw["scene_text"]
    svc.rewrite_scene = AsyncMock(side_effect=fake_rewrite)
    return svc


@pytest.mark.asyncio
async def test_extract_writes_mappings_and_traits(db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="A 李铁柱 B", intensity=2, status="ready")
    db_session.add(p); await db_session.commit()
    pipe = AdaptationPipeline(db=db_session, llm=fake_llm)
    await pipe.extract(p)
    rows = (await db_session.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
    )).scalars().all()
    assert any(r.original_text == "李铁柱" for r in rows)
    await db_session.refresh(p)
    assert p.metadata_["character_traits"][0]["name"] == "李铁柱"


@pytest.mark.asyncio
async def test_extract_preserves_locked(db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="李铁柱", intensity=1, status="ready")
    db_session.add(p); await db_session.flush()
    locked = AdaptationMappingEntry(project_id=p.id, entity_type="person",
                                     original_text="李铁柱", replacement_text="马克", locked=True)
    db_session.add(locked); await db_session.commit()

    pipe = AdaptationPipeline(db=db_session, llm=fake_llm)
    await pipe.extract(p)
    await db_session.refresh(locked)
    assert locked.replacement_text == "马克"
    assert locked.locked is True


@pytest.mark.asyncio
async def test_split_uses_llm_fallback(db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t",
                          source_text="毫无场标记的散文一段二十字", intensity=2, status="ready")
    db_session.add(p); await db_session.commit()
    pipe = AdaptationPipeline(db=db_session, llm=fake_llm)
    await pipe.split(p)
    await db_session.refresh(p)
    assert p.metadata_["split_method"] == "llm"
    assert len(p.metadata_["scene_boundaries"]) == 2


@pytest.mark.asyncio
async def test_run_full_writes_scenes_and_marks_done(db_session, test_user, fake_llm):
    p = AdaptationProject(
        user_id=test_user.id, title="t", source_text="0123456789ABCDEFGHIJ",
        intensity=2, status="ready",
        metadata_={"scene_boundaries": [
            {"index": 0, "start": 0, "end": 10, "title": "A"},
            {"index": 1, "start": 10, "end": 20, "title": "B"},
        ], "scene_summaries": ["S0", "S1"], "character_traits": []},
    )
    db_session.add(p); await db_session.commit()
    pipe = AdaptationPipeline(db=db_session, llm=fake_llm, concurrency=2)
    version = await pipe.create_full_run(p)
    await pipe.execute_full_run(p, version)
    results = (await db_session.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == version.id)
        .order_by(AdaptationSceneResult.scene_index)
    )).scalars().all()
    assert len(results) == 2
    assert all(r.status == "done" for r in results)
    assert results[0].rewritten_scene_text.startswith("改:")
    await db_session.refresh(version)
    assert version.status == "done"


@pytest.mark.asyncio
async def test_run_full_partial_when_one_scene_fails(db_session, test_user, fake_llm):
    async def fake_rewrite(**kw):
        if kw["scene_text"].startswith("0"):
            raise RuntimeError("boom")
        return "OK"
    fake_llm.rewrite_scene = AsyncMock(side_effect=fake_rewrite)

    p = AdaptationProject(
        user_id=test_user.id, title="t", source_text="0123456789ABCDEFGHIJ",
        intensity=2, status="ready",
        metadata_={"scene_boundaries": [
            {"index": 0, "start": 0, "end": 10, "title": "A"},
            {"index": 1, "start": 10, "end": 20, "title": "B"},
        ], "scene_summaries": ["", ""], "character_traits": []},
    )
    db_session.add(p); await db_session.commit()
    pipe = AdaptationPipeline(db=db_session, llm=fake_llm, concurrency=2)
    v = await pipe.create_full_run(p)
    await pipe.execute_full_run(p, v)
    await db_session.refresh(v)
    assert v.status == "partial"
    assert v.stats["failed"] == 1 and v.stats["succeeded"] == 1
