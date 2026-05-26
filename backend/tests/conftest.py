"""测试配置

- SQLite 内存库
- pytest-asyncio auto mode（见 pytest.ini），由 pytest-asyncio 自行管理事件循环
- client fixture 自动注入 get_db / get_current_user 覆盖，免去逐用例传 token
"""
import os
import sys
from typing import AsyncGenerator

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.core.database import Base


# 使用内存数据库进行测试
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="function")
async def test_engine():
    """创建测试数据库引擎"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite 默认不强制 FK CASCADE，需要手动开启
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # 注意：in-memory sqlite + StaticPool 下 dispose() 即销毁库；
    # 显式 drop_all 在 dispose 前做会触发"事件循环已关闭"竞态，故省略。
    await engine.dispose()


@pytest.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    test_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with test_session() as session:
        yield session


@pytest.fixture
def override_get_db(db_session: AsyncSession):
    """覆盖数据库依赖"""
    async def _get_db():
        yield db_session
    return _get_db


@pytest.fixture
async def sample_user(db_session: AsyncSession):
    """测试用户，用作 client 鉴权 + sample_project 所有者。"""
    from app.models.user import User

    user = User(
        username="tester",
        email="tester@example.com",
        hashed_password="x",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def client(db_session: AsyncSession, override_get_db, sample_user):
    """注入 db + 已登录用户的 TestClient。

    不进入 with 块以跳过 lifespan startup —— 否则 APScheduler 全局单例
    会绑死第一个测试的 event loop，第二个测试调用即 'Event loop is closed'。
    init_db / scheduler 在测试里都不需要：表由 test_engine fixture create_all，
    定时任务被显式覆盖的 db / current_user 旁路。
    """
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db
    from app.routers.auth import get_current_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: sample_user

    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
async def sample_project(db_session: AsyncSession, sample_user):
    """创建示例项目（归属 sample_user）。"""
    from app.models.project import Project

    project = Project(
        owner_id=sample_user.id,
        title="测试小说",
        genre="玄幻",
        description="这是一个测试用的小说项目",
        status="draft",
        current_word_count=0,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
async def sample_chapter(db_session: AsyncSession, sample_project):
    """创建示例章节"""
    from app.models.chapter import Chapter

    chapter = Chapter(
        project_id=sample_project.id,
        title="第一章 测试章节",
        content="这是测试章节的内容。",
        sort_order=1,
        word_count=10,
        status="draft",
    )
    db_session.add(chapter)
    await db_session.commit()
    await db_session.refresh(chapter)
    return chapter


@pytest.fixture
async def sample_character(db_session: AsyncSession, sample_project):
    """创建示例角色"""
    from app.models.character import Character

    character = Character(
        project_id=sample_project.id,
        name="测试角色",
        role_type="主角",
        gender="男",
        personality_traits="勇敢、善良",
    )
    db_session.add(character)
    await db_session.commit()
    await db_session.refresh(character)
    return character
