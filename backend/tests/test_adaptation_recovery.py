"""启动恢复 hook 测试。"""
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.user import User
from app.services.adaptation_recovery import cleanup_stale_runs


@pytest.fixture
async def test_user(db_session):
    user = User(username="recovery_tester", email="rec@test.com", hashed_password="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_cleanup_marks_old_running_as_failed(db_session, test_user):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="generating")
    db_session.add(p); await db_session.flush()
    old = AdaptationVersion(
        project_id=p.id, version_no=1, status="running", triggered_by="full_run",
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    fresh = AdaptationVersion(
        project_id=p.id, version_no=2, status="running", triggered_by="full_run",
    )
    db_session.add_all([old, fresh]); await db_session.flush()
    db_session.add(AdaptationSceneResult(
        version_id=old.id, scene_index=0, original_scene_text="x", status="running"
    ))
    await db_session.commit()

    await cleanup_stale_runs(db_session, max_age_sec=3600)
    await db_session.refresh(old); await db_session.refresh(fresh)
    assert old.status == "failed" and old.error
    assert fresh.status == "running"
    s = (await db_session.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == old.id)
    )).scalar_one()
    assert s.status == "failed"
