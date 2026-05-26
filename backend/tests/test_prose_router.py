"""prose router 测试 —— 全程 mock pipeline"""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.prose_project import ProseProject, ProseScene
from app.models.script_project import ScriptProject
from app.models.user import User


@pytest.fixture
async def script_project(db_session, sample_user):
    sp = ScriptProject(
        user_id=sample_user.id, title="测试剧本", script_type="dynamic"
    )
    db_session.add(sp)
    await db_session.commit()
    await db_session.refresh(sp)
    return sp


@pytest.fixture
async def prose_project(db_session, sample_user, script_project):
    p = ProseProject(
        user_id=sample_user.id,
        title="测试散文项目",
        script_project_id=script_project.id,
        premise="一个都市爱情故事",
        status="done",
        total_scenes=2,
        done_scenes=2,
    )
    db_session.add(p)
    await db_session.flush()
    db_session.add_all([
        ProseScene(project_id=p.id, scene_index=0, scene_title="场1",
                   original_scene_text="原文1", prose_text="散文1", status="done"),
        ProseScene(project_id=p.id, scene_index=1, scene_title="场2",
                   original_scene_text="原文2", prose_text="散文2", status="done"),
    ])
    await db_session.commit()
    await db_session.refresh(p)
    return p


@pytest.mark.asyncio
async def test_create_prose_project_returns_pending(client, db_session, script_project):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post("/api/v1/prose", json={
            "script_project_id": script_project.id,
            "premise": "都市爱情故事",
            "title": "我的散文",
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["script_project_id"] == script_project.id
    assert body["premise"] == "都市爱情故事"


@pytest.mark.asyncio
async def test_create_returns_400_if_script_not_found(client):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post("/api/v1/prose", json={
            "script_project_id": 99999,
            "premise": "测试梗概",
        })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_returns_user_projects(client, db_session, prose_project):
    resp = client.get("/api/v1/prose")
    assert resp.status_code == 200
    items = resp.json()
    assert any(p["id"] == prose_project.id for p in items)
    assert all("scenes" not in p for p in items)


@pytest.mark.asyncio
async def test_detail_returns_scenes(client, prose_project):
    resp = client.get(f"/api/v1/prose/{prose_project.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == prose_project.id
    assert len(body["scenes"]) == 2
    assert body["scenes"][0]["prose_text"] == "散文1"


@pytest.mark.asyncio
async def test_detail_404(client):
    resp = client.get("/api/v1/prose/99999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_cascades_scenes(client, db_session, prose_project):
    resp = client.delete(f"/api/v1/prose/{prose_project.id}")
    assert resp.status_code == 204

    from sqlalchemy import select
    remaining = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == prose_project.id)
    )).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_delete_404(client):
    resp = client.delete("/api/v1/prose/99999")
    assert resp.status_code == 404
