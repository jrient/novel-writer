"""canon router：启动提取（mock pipeline）+ 实体 CRUD + 并发守卫"""
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity, CanonExtractionJob


@pytest.fixture
async def ref(db_session, sample_user):
    r = ReferenceNovel(title="原作A", owner_id=sample_user.id, content="正文", total_chars=10)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


@pytest.mark.asyncio
async def test_list_entities_empty(client, ref):
    resp = client.get(f"/api/v1/references/{ref.id}/canon/entities")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_and_update_and_delete_entity(client, ref):
    r = client.post(f"/api/v1/references/{ref.id}/canon/entities",
        json={"entity_type": "character", "canonical_name": "孙悟空"})
    assert r.status_code == 201
    eid = r.json()["id"]
    assert r.json()["review_status"] == "user_added"

    r2 = client.put(f"/api/v1/references/{ref.id}/canon/entities/{eid}",
        json={"summary": "齐天大圣"})
    assert r2.status_code == 200
    assert r2.json()["summary"] == "齐天大圣"
    assert r2.json()["review_status"] == "user_edited"

    r3 = client.delete(f"/api/v1/references/{ref.id}/canon/entities/{eid}")
    assert r3.status_code == 204


@pytest.mark.asyncio
async def test_start_extraction_triggers_pipeline(client, ref):
    with patch("app.routers.canon.run_canon_extraction",
               new=AsyncMock(return_value=123)):
        with patch("app.routers.canon.asyncio.create_task") as ct:
            resp = client.post(f"/api/v1/references/{ref.id}/canon/extract")
    assert resp.status_code == 202
    assert ct.called


@pytest.mark.asyncio
async def test_stream_requires_valid_ticket(client, ref):
    # 无效 ticket 应被拒绝
    resp = client.get(f"/api/v1/references/{ref.id}/canon/stream?ticket=bogus")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_stream_ticket_returns_ticket_for_owner(client, ref):
    resp = client.post(f"/api/v1/references/{ref.id}/canon/stream/ticket")
    assert resp.status_code == 200
    assert resp.json().get("ticket")


@pytest.mark.asyncio
async def test_stream_emits_snapshot_and_terminates_for_finished_job(
    client, ref, db_session, test_engine
):
    """已结束的 job：SSE 应补发 snapshot 首帧并立即下发终止事件、关闭流（不挂起）。
    这是修复「订阅晚于任务启动」竞态的回归测试。"""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    job = CanonExtractionJob(
        reference_id=ref.id, status="done",
        chunk_total=3, chunk_done=3, failed_chunks=0, entity_count=7,
    )
    db_session.add(job)
    await db_session.commit()

    # 快照走模块级 async_session（绑定真实引擎）；测试里指向 test_engine 才能看到该 job
    test_sm = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    ticket = client.post(f"/api/v1/references/{ref.id}/canon/stream/ticket").json()["ticket"]
    with patch("app.routers.canon.async_session", new=test_sm):
        resp = client.get(f"/api/v1/references/{ref.id}/canon/stream?ticket={ticket}")
    assert resp.status_code == 200
    body = resp.text
    assert '"event": "snapshot"' in body
    assert '"entity_count": 7' in body
    assert '"event": "done"' in body


@pytest.mark.asyncio
async def test_start_extraction_rejects_when_in_flight(client, ref, db_session):
    # 预置一个 processing 中的 job
    job = CanonExtractionJob(reference_id=ref.id, status="processing")
    db_session.add(job)
    await db_session.commit()
    with patch("app.routers.canon.asyncio.create_task") as ct:
        resp = client.post(f"/api/v1/references/{ref.id}/canon/extract")
    assert resp.status_code == 409
    assert not ct.called  # 不应再启动新任务

@pytest.mark.asyncio
async def test_relation_crud(client, ref, db_session):
    from app.models.canon import CanonEntity
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="乙")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)

    # create
    r = client.post(f"/api/v1/references/{ref.id}/canon/relations", json={
        "source_entity_id": a.id, "target_entity_id": b.id,
        "relation_type": "师徒", "label": "甲是乙的师父"})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["review_status"] == "user_added"

    # list
    r = client.get(f"/api/v1/references/{ref.id}/canon/relations")
    assert r.status_code == 200 and len(r.json()) == 1

    # update → user_edited
    r = client.put(f"/api/v1/references/{ref.id}/canon/relations/{rid}",
                   json={"label": "改了"})
    assert r.status_code == 200 and r.json()["label"] == "改了"
    assert r.json()["review_status"] == "user_edited"

    # delete
    r = client.delete(f"/api/v1/references/{ref.id}/canon/relations/{rid}")
    assert r.status_code == 204
    r = client.get(f"/api/v1/references/{ref.id}/canon/relations")
    assert len(r.json()) == 0

@pytest.mark.asyncio
async def test_graph_endpoint(client, ref, db_session):
    from app.models.canon import CanonEntity, CanonRelation
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="faction", canonical_name="某派")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)
    db_session.add(CanonRelation(reference_id=ref.id, source_entity_id=a.id,
                                 target_entity_id=b.id, relation_type="属于"))
    await db_session.commit()
    r = client.get(f"/api/v1/references/{ref.id}/canon/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 2 and len(body["edges"]) == 1


@pytest.mark.asyncio
async def test_extract_relations_requires_entities(client, ref):
    # 无实体时拒绝
    r = client.post(f"/api/v1/references/{ref.id}/canon/extract-relations")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_extract_relations_triggers(client, ref, db_session):
    from unittest.mock import patch, AsyncMock
    from app.models.canon import CanonEntity
    db_session.add(CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲"))
    await db_session.commit()
    with patch("app.routers.canon.extract_relations_for_reference",
               new=AsyncMock(return_value=0)) as m:
        r = client.post(f"/api/v1/references/{ref.id}/canon/extract-relations")
    assert r.status_code == 202
