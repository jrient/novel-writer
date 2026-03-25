"""
剧本模型测试
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.script_project import ScriptProject
from app.models.script_node import ScriptNode
from app.models.script_session import ScriptSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """创建测试用户"""
    user = User(
        username="drama_tester",
        email="drama@test.com",
        hashed_password="hashed_pw",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def sample_script_project(db_session: AsyncSession, test_user: User) -> ScriptProject:
    """创建示例剧本项目"""
    project = ScriptProject(
        user_id=test_user.id,
        title="测试剧本",
        script_type="dynamic",
        concept="一个关于时间旅行的故事",
        status="drafting",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
async def sample_script_node(db_session: AsyncSession, sample_script_project: ScriptProject) -> ScriptNode:
    """创建示例剧本节点"""
    node = ScriptNode(
        project_id=sample_script_project.id,
        node_type="episode",
        title="第一集",
        content="开场内容",
        sort_order=1,
    )
    db_session.add(node)
    await db_session.commit()
    await db_session.refresh(node)
    return node


# ---------------------------------------------------------------------------
# ScriptProject 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_script_project(db_session: AsyncSession, test_user: User):
    """测试创建剧本项目"""
    project = ScriptProject(
        user_id=test_user.id,
        title="说明类剧本",
        script_type="explanatory",
        concept="科普讲解量子力学",
        status="drafting",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    assert project.id is not None
    assert project.title == "说明类剧本"
    assert project.script_type == "explanatory"
    assert project.status == "drafting"
    assert project.created_at is not None


@pytest.mark.asyncio
async def test_script_project_defaults(db_session: AsyncSession, test_user: User):
    """测试剧本项目默认值"""
    project = ScriptProject(
        user_id=test_user.id,
        title="默认项目",
        script_type="dynamic",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    assert project.status == "drafting"
    assert project.ai_config is None
    assert project.metadata_ is None


@pytest.mark.asyncio
async def test_script_project_with_json_fields(db_session: AsyncSession, test_user: User):
    """测试带 JSON 字段的剧本项目"""
    ai_config = {"provider": "openai", "model": "gpt-4"}
    metadata = {"tags": ["科幻", "冒险"], "priority": 1}

    project = ScriptProject(
        user_id=test_user.id,
        title="带配置项目",
        script_type="dynamic",
        ai_config=ai_config,
        metadata_=metadata,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    assert project.ai_config == ai_config
    assert project.metadata_ == metadata


@pytest.mark.asyncio
async def test_script_project_cascade_delete(db_session: AsyncSession, test_user: User):
    """测试项目级联删除节点"""
    project = ScriptProject(
        user_id=test_user.id,
        title="将被删除的项目",
        script_type="dynamic",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    node = ScriptNode(
        project_id=project.id,
        node_type="episode",
        title="节点",
    )
    db_session.add(node)
    await db_session.commit()

    node_id = node.id
    project_id = project.id

    await db_session.delete(project)
    await db_session.commit()

    # 节点应已被级联删除
    from sqlalchemy import select
    result = await db_session.execute(
        select(ScriptNode).where(ScriptNode.id == node_id)
    )
    assert result.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# ScriptNode 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_script_node(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试创建剧本节点"""
    node = ScriptNode(
        project_id=sample_script_project.id,
        node_type="dialogue",
        title="对话节点",
        content="你好，世界！",
        speaker="主角",
        sort_order=1,
    )
    db_session.add(node)
    await db_session.commit()
    await db_session.refresh(node)

    assert node.id is not None
    assert node.node_type == "dialogue"
    assert node.speaker == "主角"
    assert node.is_completed is False
    assert node.parent_id is None


@pytest.mark.asyncio
async def test_script_node_parent_child(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试节点父子关系"""
    parent = ScriptNode(
        project_id=sample_script_project.id,
        node_type="episode",
        title="父节点",
        sort_order=0,
    )
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    child = ScriptNode(
        project_id=sample_script_project.id,
        parent_id=parent.id,
        node_type="scene",
        title="子节点",
        sort_order=0,
    )
    db_session.add(child)
    await db_session.commit()
    await db_session.refresh(child)

    assert child.parent_id == parent.id


@pytest.mark.asyncio
async def test_script_node_all_types(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试所有合法节点类型"""
    node_types = [
        "episode", "scene", "dialogue", "action", "effect",
        "inner_voice", "section", "narration", "intro",
    ]
    for i, nt in enumerate(node_types):
        node = ScriptNode(
            project_id=sample_script_project.id,
            node_type=nt,
            sort_order=i,
        )
        db_session.add(node)

    await db_session.commit()

    from sqlalchemy import select
    result = await db_session.execute(
        select(ScriptNode).where(ScriptNode.project_id == sample_script_project.id)
    )
    nodes = result.scalars().all()
    assert len(nodes) == len(node_types)


@pytest.mark.asyncio
async def test_script_node_defaults(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试节点默认值"""
    node = ScriptNode(
        project_id=sample_script_project.id,
        node_type="action",
    )
    db_session.add(node)
    await db_session.commit()
    await db_session.refresh(node)

    assert node.sort_order == 0
    assert node.is_completed is False
    assert node.title is None
    assert node.content is None
    assert node.speaker is None
    assert node.metadata_ is None


# ---------------------------------------------------------------------------
# ScriptSession 测试
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_script_session(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试创建剧本会话"""
    session = ScriptSession(
        project_id=sample_script_project.id,
        state="init",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.id is not None
    assert session.state == "init"
    assert session.project_id == sample_script_project.id
    assert session.created_at is not None


@pytest.mark.asyncio
async def test_script_session_defaults(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试会话默认值"""
    session = ScriptSession(
        project_id=sample_script_project.id,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.state == "init"
    assert session.outline_draft is None
    assert session.current_node_id is None


@pytest.mark.asyncio
async def test_script_session_with_history(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试带历史记录的会话"""
    history = [
        {"role": "assistant", "content": "请描述你的创意"},
        {"role": "user", "content": "一个时间旅行的故事"},
    ]
    session = ScriptSession(
        project_id=sample_script_project.id,
        state="collecting",
        history=history,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.history == history
    assert session.state == "collecting"


@pytest.mark.asyncio
async def test_script_session_unique_per_project(db_session: AsyncSession, sample_script_project: ScriptProject):
    """测试每个项目只能有一个会话"""
    session1 = ScriptSession(
        project_id=sample_script_project.id,
        state="init",
    )
    db_session.add(session1)
    await db_session.commit()

    session2 = ScriptSession(
        project_id=sample_script_project.id,
        state="collecting",
    )
    db_session.add(session2)

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await db_session.commit()

    await db_session.rollback()


@pytest.mark.asyncio
async def test_session_with_current_node(db_session: AsyncSession, sample_script_project: ScriptProject, sample_script_node: ScriptNode):
    """测试会话关联当前节点"""
    session = ScriptSession(
        project_id=sample_script_project.id,
        state="generating",
        current_node_id=sample_script_node.id,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    assert session.current_node_id == sample_script_node.id
