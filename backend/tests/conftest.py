"""
测试配置
使用内存数据库和依赖覆盖
"""
import pytest
import asyncio
from typing import AsyncGenerator
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from app.core.database import Base


# 使用内存数据库进行测试
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def test_engine():
    """创建测试数据库引擎"""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


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
async def client(db_session: AsyncSession, override_get_db):
    """创建测试客户端"""
    from fastapi.testclient import TestClient
    from app.main import app
    from app.core.database import get_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def sample_project(db_session: AsyncSession):
    """创建示例项目"""
    from app.models.project import Project

    project = Project(
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