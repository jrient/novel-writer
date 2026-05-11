"""改编模块模型基础持久化测试。"""
import pytest
from sqlalchemy import select
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.user import User


@pytest.fixture
async def test_user(db_session):
    """创建测试用户。"""
    user = User(username="adapt_tester", email="adapt@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_adaptation_project_persist(db_session, test_user):
    project = AdaptationProject(
        user_id=test_user.id,
        title="改编测试",
        source_text="原文一二三",
        intensity=2,
        status="ready",
        metadata_={"scene_boundaries": [{"index": 0, "start": 0, "end": 5, "title": "场1"}]},
    )
    db_session.add(project)
    await db_session.commit()

    found = (await db_session.execute(
        select(AdaptationProject).where(AdaptationProject.id == project.id)
    )).scalar_one()
    assert found.title == "改编测试"
    assert found.metadata_["scene_boundaries"][0]["title"] == "场1"


@pytest.mark.asyncio
async def test_adaptation_full_cascade(db_session, test_user):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="ready")
    db_session.add(p); await db_session.flush()

    m = AdaptationMappingEntry(
        project_id=p.id, entity_type="person",
        original_text="李铁柱", replacement_text="马克", locked=True, order_index=0,
    )
    v = AdaptationVersion(
        project_id=p.id, version_no=1, triggered_by="full_run",
        status="running", mapping_snapshot=[{"original_text": "李铁柱", "replacement_text": "马克"}],
    )
    db_session.add_all([m, v]); await db_session.flush()

    s = AdaptationSceneResult(
        version_id=v.id, scene_index=0,
        original_scene_text="原文", scene_title="场1", status="pending",
    )
    db_session.add(s); await db_session.commit()

    pid = p.id
    await db_session.delete(p); await db_session.commit()
    remaining = (await db_session.execute(
        select(AdaptationVersion).where(AdaptationVersion.project_id == pid)
    )).scalars().all()
    assert remaining == []
