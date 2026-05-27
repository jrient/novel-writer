"""prose router 测试 —— 全程 mock pipeline"""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.prose_project import ProseProject, ProseScene
from app.models.user import User


@pytest.fixture
async def prose_project(db_session, sample_user):
    p = ProseProject(
        user_id=sample_user.id,
        title="测试散文项目",
        script_project_id=None,
        script_project_title="test.txt",
        script_content="第一段内容。\n\n第二段内容。",
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
async def test_create_prose_project_returns_pending(client):
    txt = b"\xe7\xac\xac\xe4\xb8\x80\xe6\xae\xb5\xe5\x86\x85\xe5\xae\xb9\n\n\xe7\xac\xac\xe4\xba\x8c\xe6\xae\xb5\xe5\x86\x85\xe5\xae\xb9"
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post(
            "/api/v1/prose",
            data={"premise": "都市爱情故事", "title": "我的散文"},
            files={"file": ("test.txt", txt, "text/plain")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["script_project_id"] is None
    assert body["premise"] == "都市爱情故事"
    assert body["title"] == "我的散文"


@pytest.mark.asyncio
async def test_create_returns_400_on_unsupported_format(client):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post(
            "/api/v1/prose",
            data={"premise": "测试梗概"},
            files={"file": ("test.pdf", b"pdf content", "application/pdf")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_returns_400_on_empty_file(client):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post(
            "/api/v1/prose",
            data={"premise": "测试梗概"},
            files={"file": ("empty.txt", b"   ", "text/plain")},
        )
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
