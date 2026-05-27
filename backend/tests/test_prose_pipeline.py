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


@pytest.mark.asyncio
async def test_pipeline_creates_scenes_and_marks_done(
    db_session, session_factory, test_user, script_with_nodes
):
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
    fake_provider.complete = AsyncMock(return_value="散文改写结果")

    fake_search = AsyncMock(return_value=[
        {"sample_id": 1, "title": "样本A",
         "prompt_fragment": "风格指南", "prose_excerpt": "节选段落"}
    ])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.total_scenes == 3
    assert project.done_scenes == 3
    assert project.failed_scenes == 0

    scenes = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == project.id)
        .order_by(ProseScene.scene_index)
    )).scalars().all()
    assert len(scenes) == 3
    assert all(s.status == "done" for s in scenes)
    assert all(s.prose_text == "散文改写结果" for s in scenes)


@pytest.mark.asyncio
async def test_pipeline_partial_failure(
    db_session, session_factory, test_user, script_with_nodes
):
    project = ProseProject(
        user_id=test_user.id,
        title="部分失败测试",
        script_project_id=script_with_nodes.id,
        premise="测试梗概",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    call_count = 0

    async def flaky_complete(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("LLM 失败")
        return "散文结果"

    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(side_effect=flaky_complete)
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "partial"
    assert project.failed_scenes == 1
    assert project.done_scenes == 2


@pytest.mark.asyncio
async def test_pipeline_degraded_no_samples(
    db_session, session_factory, test_user, script_with_nodes
):
    """样本库为空时降级继续生成"""
    project = ProseProject(
        user_id=test_user.id,
        title="降级测试",
        script_project_id=script_with_nodes.id,
        premise="梗概",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="降级散文")
    fake_search = AsyncMock(return_value=[])  # 空结果

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.style_snapshot == "[]"


def test_split_content_heading_based():
    """有场景标题时应按标题行分组"""
    from app.services.prose_pipeline import _split_content_to_scenes
    text = "第一场 开场\n主角登场，走进房间。\n\n第二场 冲突\n两人争吵激烈。\n\n第三场 结局\n和解收场。"
    scenes = _split_content_to_scenes(text)
    assert len(scenes) == 3
    assert scenes[0][0] == "第一场 开场"
    assert "主角登场" in scenes[0][1]
    assert scenes[1][0] == "第二场 冲突"


def test_split_content_no_headings_merges_to_batches():
    """无标题时，段落应合并为 TARGET_BATCHES 个批次，不产生微场景"""
    from app.services.prose_pipeline import _split_content_to_scenes, TARGET_BATCHES
    short_para = "女主：你好，好久不见呀。"  # 短对白行
    text = "\n\n".join([short_para] * 40)
    scenes = _split_content_to_scenes(text)
    assert len(scenes) == TARGET_BATCHES


def test_split_content_many_scenes_merged_to_batches():
    """20个场景标题应合并为 TARGET_BATCHES 个批次"""
    from app.services.prose_pipeline import _split_content_to_scenes, TARGET_BATCHES
    lines = [f"1-{i} 场景{i} 夜\n内容描述。" for i in range(1, 21)]
    text = "\n\n".join(lines)
    scenes = _split_content_to_scenes(text)
    assert len(scenes) == TARGET_BATCHES


@pytest.mark.asyncio
async def test_pipeline_split_content_path(
    db_session, session_factory, test_user
):
    """script_content 路径：有标题行时按标题分组为场景"""
    # 使用明确的场景标题，触发策略1（标题分组）
    script = (
        "第一场 相遇\n女主走进咖啡馆，看到一个熟悉的背影……\n\n"
        "第二场 对话\n两人相视一笑，话题从工作聊到了往事。\n\n"
        "第三场 离别\n咖啡喝完，两人各自散去，心里都留下了一丝惆怅。"
    )
    project = ProseProject(
        user_id=test_user.id,
        title="上传文件散文",
        script_project_id=None,
        script_content=script,
        premise="测试梗概",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="散文改写结果")
    fake_search = AsyncMock(return_value=[])

    from app.services import prose_pipeline
    with patch.object(prose_pipeline, "_search_style_samples", fake_search):
        await prose_pipeline.run(session_factory, project.id, provider=fake_provider)

    await db_session.refresh(project)
    assert project.status == "done"
    assert project.total_scenes == 3
    assert project.done_scenes == 3

    scenes = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == project.id)
        .order_by(ProseScene.scene_index)
    )).scalars().all()
    assert len(scenes) == 3
    assert scenes[0].scene_title == "第一场 相遇"


@pytest.mark.asyncio
async def test_pipeline_empty_script_marks_failed(
    db_session, session_factory, test_user
):
    """剧本无节点内容时 → status=failed"""
    sp = ScriptProject(
        user_id=test_user.id, title="空剧本", script_type="dynamic"
    )
    db_session.add(sp)
    await db_session.commit()

    project = ProseProject(
        user_id=test_user.id, title="空剧本散文",
        script_project_id=sp.id, premise="测试"
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
