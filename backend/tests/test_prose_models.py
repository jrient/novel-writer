import pytest
from sqlalchemy import select
from app.models.prose_project import ProseProject, ProseScene
from app.models.user import User


@pytest.fixture
async def test_user(db_session):
    u = User(username="prose_tester", email="prose@test.com", hashed_password="x")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_prose_project_minimal(db_session, test_user):
    p = ProseProject(
        user_id=test_user.id,
        title="测试散文",
        script_project_id=99,
        premise="一个都市爱情故事",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    assert p.id > 0
    assert p.status == "pending"
    assert p.total_scenes == 0
    assert p.done_scenes == 0
    assert p.failed_scenes == 0


@pytest.mark.asyncio
async def test_scene_cascade_delete(db_session, test_user):
    p = ProseProject(
        user_id=test_user.id, title="x", script_project_id=1, premise="p"
    )
    db_session.add(p)
    await db_session.flush()
    s = ProseScene(
        project_id=p.id,
        scene_index=0,
        scene_title="场1",
        original_scene_text="原文",
    )
    db_session.add(s)
    await db_session.commit()

    await db_session.delete(p)
    await db_session.commit()

    remaining = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == p.id)
    )).scalars().all()
    assert remaining == []
