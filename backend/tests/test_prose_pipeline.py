# backend/tests/test_prose_pipeline.py
"""prose_pipeline 测试：mock LLM provider + mock style search"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.prose_project import ProseProject, ProseScene
from app.models.script_project import ScriptProject
from app.models.script_node import ScriptNode
from app.models.user import User


@pytest.fixture
async def test_user(db_session):
    u = User(username="prose_pipe", email="prosepipe@test.com", hashed_password="x")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.fixture
async def script_with_nodes(db_session, test_user):
    sp = ScriptProject(
        user_id=test_user.id, title="测试剧本", script_type="dynamic"
    )
    db_session.add(sp)
    await db_session.flush()
    nodes = [
        ScriptNode(project_id=sp.id, node_type="scene", title=f"场{i+1}",
                   content=f"场次{i+1}原文内容", sort_order=i)
        for i in range(3)
    ]
    db_session.add_all(nodes)
    await db_session.commit()
    await db_session.refresh(sp)
    return sp


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


# ── _parse_outline_chapters 单元测试 ───────────────────────────────────────────

def test_parse_outline_chapters_normal():
    from app.services.prose_pipeline import _parse_outline_chapters
    outline = (
        "第一章：相遇\n女主走进咖啡馆，看到熟悉的背影。\n\n"
        "第二章：冲突\n两人争吵，往事浮现。\n\n"
        "第三章：和解\n误会消除，感情升温。"
    )
    chapters = _parse_outline_chapters(outline)
    assert len(chapters) == 3
    assert chapters[0][0] == "第一章：相遇"
    assert "女主走进咖啡馆" in chapters[0][1]
    assert chapters[2][0] == "第三章：和解"


def test_parse_outline_chapters_no_headings_returns_single():
    from app.services.prose_pipeline import _parse_outline_chapters
    chapters = _parse_outline_chapters("没有章节标题的大纲文本。")
    assert len(chapters) == 1
    assert chapters[0][0] == "第一章"


# ── Pipeline 集成测试 ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_creates_chapters_and_marks_done(
    db_session, session_factory, test_user, script_with_nodes
):
    """从剧本节点路径：生成大纲 → 3章 → status=done"""
    project = ProseProject(
        user_id=test_user.id,
        title="散文测试",
        script_project_id=script_with_nodes.id,
        premise="都市爱情",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    fake_provider = AsyncMock()
    outline_text = "第一章：相遇\n内容。\n\n第二章：冲突\n内容。\n\n第三章：结局\n内容。"
    # 第一次调用返回大纲，后续调用返回章节散文
    call_count = 0
    async def fake_complete(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return outline_text
        return f"散文改写结果第{call_count - 1}章"
    fake_provider.complete = AsyncMock(side_effect=fake_complete)

    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.total_scenes == 3
    assert project.done_scenes == 3
    assert project.outline == outline_text

    scenes = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == project.id)
        .order_by(ProseScene.scene_index)
    )).scalars().all()
    assert len(scenes) == 3
    assert all(s.status == "done" for s in scenes)
    assert scenes[0].scene_title == "第一章：相遇"


@pytest.mark.asyncio
async def test_pipeline_upload_path(
    db_session, session_factory, test_user
):
    """从上传文件路径（script_content）：同样走大纲流程"""
    script = "1-1 医院急救室外 夜\n主角痛苦地等待。\n\n1-2 走廊\n消息传来，他崩溃了。"
    project = ProseProject(
        user_id=test_user.id,
        title="上传散文",
        script_project_id=None,
        script_content=script,
        premise="家庭悲剧",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    fake_provider = AsyncMock()
    call_count = 0
    async def fake_complete(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "第一章：悲痛\n主角经历了生命中最艰难的夜晚。\n\n第二章：重生\n他在废墟中找到了力量。"
        return f"章节散文{call_count}"
    fake_provider.complete = AsyncMock(side_effect=fake_complete)
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.total_scenes == 2
    assert project.outline is not None


@pytest.mark.asyncio
async def test_pipeline_outline_failure_falls_back(
    db_session, session_factory, test_user
):
    """大纲生成失败时，降级为单章继续生成"""
    project = ProseProject(
        user_id=test_user.id,
        title="大纲降级测试",
        script_project_id=None,
        script_content="场景内容。",
        premise="测试故事",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    call_count = 0
    async def fake_complete(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("LLM timeout")
        return "降级散文内容"
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=fake_complete)
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.total_scenes == 1


@pytest.mark.asyncio
async def test_pipeline_chapter_partial_failure(
    db_session, session_factory, test_user
):
    """一章失败时 status=partial"""
    project = ProseProject(
        user_id=test_user.id,
        title="部分失败",
        script_project_id=None,
        script_content="内容。",
        premise="测试",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    call_count = 0
    async def fake_complete(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return "第一章：开始\n内容。\n\n第二章：结束\n内容。"
        if call_count == 2:
            return "第一章散文"
        raise RuntimeError("章节LLM失败")
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=fake_complete)
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "partial"
    assert project.done_scenes == 1
    assert project.failed_scenes == 1


@pytest.mark.asyncio
async def test_pipeline_empty_script_marks_failed(
    db_session, session_factory, test_user
):
    """空内容直接 status=failed"""
    project = ProseProject(
        user_id=test_user.id,
        title="空内容",
        script_project_id=None,
        script_content="   ",
        premise="测试",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    fake_provider = AsyncMock()
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "failed"
