"""style_sample router 测试 —— 全程 mock pipeline 与 ai/embedding"""
from unittest.mock import AsyncMock, patch

import pytest


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
