"""style_sample router 测试 —— 全程 mock pipeline 与 ai/embedding"""
import json
from unittest.mock import AsyncMock, patch

import pytest

from app.models.style_sample import StyleSample


@pytest.mark.asyncio
async def test_upload_creates_sample_pending(client, db_session):
    """上传 → 同步返回 sample_id + pending 状态；pipeline 调用被 mock"""
    content_bytes = ("正文内容" * 100).encode("utf-8")
    files = {"file": ("test.txt", content_bytes, "text/plain")}
    data = {"title": "测试标题", "genre": "都市言情"}

    with patch("app.routers.style_sample.style_sample_pipeline.run", new=AsyncMock()) as mock_run:
        resp = client.post("/api/v1/style-samples", files=files, data=data)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["title"] == "测试标题"
    assert body["genre"] == "都市言情"
    assert body["index_status"] == "pending"
    assert body["id"] > 0
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_format(client):
    files = {"file": ("evil.exe", b"\x00\x01", "application/octet-stream")}
    data = {"title": "x"}
    resp = client.post("/api/v1/style-samples", files=files, data=data)
    assert resp.status_code == 400
    assert "格式" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_upload_requires_title(client):
    files = {"file": ("t.txt", "abc".encode("utf-8"), "text/plain")}
    resp = client.post("/api/v1/style-samples", files=files, data={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_returns_summaries_filterable(client, db_session):
    db_session.add_all([
        StyleSample(title="A 都市", genre="都市言情", content="x"),
        StyleSample(title="B 悬疑", genre="悬疑", content="y"),
    ])
    await db_session.commit()

    resp = client.get("/api/v1/style-samples")
    assert resp.status_code == 200
    items = resp.json()
    assert {it["title"] for it in items} == {"A 都市", "B 悬疑"}
    assert "content" not in items[0]

    resp = client.get("/api/v1/style-samples?genre=都市言情")
    assert [it["title"] for it in resp.json()] == ["A 都市"]


@pytest.mark.asyncio
async def test_detail_returns_content_and_parsed_guide(client, db_session):
    guide = json.dumps({
        "structured": {"pov": "第一人称", "signature_devices": []},
        "prose_excerpt": "节选...",
        "prompt_fragment": "片段...",
    }, ensure_ascii=False)
    s = StyleSample(
        title="详情用",
        content="原文全文 1234",
        style_guide=guide,
        extraction_model="test-model",
        index_status="ready",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    resp = client.get(f"/api/v1/style-samples/{s.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "原文全文 1234"
    assert body["style_guide"]["structured"]["pov"] == "第一人称"
    assert body["style_guide"]["prompt_fragment"] == "片段..."


@pytest.mark.asyncio
async def test_detail_404(client):
    resp = client.get("/api/v1/style-samples/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_cascades_chunks(client, db_session):
    from app.models.style_sample import StyleSampleChunk
    from sqlalchemy import select as _sel

    s = StyleSample(title="del", content="x")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    db_session.add(StyleSampleChunk(sample_id=s.id, chunk_index=0, content="片", char_count=1))
    await db_session.commit()

    resp = client.delete(f"/api/v1/style-samples/{s.id}")
    assert resp.status_code == 204

    remaining = (await db_session.execute(_sel(StyleSampleChunk))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_reindex_resets_status_and_runs_pipeline(client, db_session):
    s = StyleSample(title="re", content="x", index_status="failed", index_error="boom")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    with patch("app.routers.style_sample.style_sample_pipeline.run", new=AsyncMock()) as mock_run:
        resp = client.post(f"/api/v1/style-samples/{s.id}/reindex")
    assert resp.status_code == 200
    assert resp.json()["index_status"] == "pending"
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_404(client):
    resp = client.delete("/api/v1/style-samples/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_search_returns_top_k_grouped_by_sample(client, db_session, monkeypatch):
    """search 应按 sample 折叠去重，返回 (sample, top_chunks)"""
    from app.models.style_sample import StyleSampleChunk

    guide = json.dumps({
        "structured": {"pov": "第一人称"}, "prose_excerpt": "...", "prompt_fragment": "frag"
    }, ensure_ascii=False)

    s1 = StyleSample(title="一", genre="都市言情", content="x", style_guide=guide, index_status="ready")
    s2 = StyleSample(title="二", genre="都市言情", content="y", style_guide=guide, index_status="ready")
    s3 = StyleSample(title="三 悬疑", genre="悬疑", content="z", style_guide=guide, index_status="ready")
    db_session.add_all([s1, s2, s3])
    await db_session.commit()
    for s in (s1, s2, s3):
        await db_session.refresh(s)

    db_session.add_all([
        StyleSampleChunk(sample_id=s1.id, chunk_index=0, content="一甲", char_count=2, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s1.id, chunk_index=1, content="一乙", char_count=2, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s2.id, chunk_index=0, content="二", char_count=1, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s3.id, chunk_index=0, content="三", char_count=1, embedding=[0.0] * 1536),
    ])
    await db_session.commit()

    async def fake_embed(text):
        return [0.0] * 1536

    monkeypatch.setattr(
        "app.routers.style_sample.embedding_service.generate_embedding", fake_embed
    )

    resp = client.post("/api/v1/style-samples/search", json={
        "query": "测试", "top_k": 5, "filter": {"genre": "都市言情"}
    })
    assert resp.status_code == 200
    hits = resp.json()
    titles = {h["sample"]["title"] for h in hits}
    assert titles == {"一", "二"}
    s1_hit = next(h for h in hits if h["sample"]["title"] == "一")
    assert len(s1_hit["top_chunks"]) == 2
    assert s1_hit["style_guide"]["prompt_fragment"] == "frag"


@pytest.mark.asyncio
async def test_search_empty_query_400(client):
    resp = client.post("/api/v1/style-samples/search", json={"query": "", "top_k": 5})
    assert resp.status_code == 422
