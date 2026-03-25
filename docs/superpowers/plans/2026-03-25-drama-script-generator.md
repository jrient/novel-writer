# Drama Script Generator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully independent drama script generation module that supports creating explanatory manga scripts (narration-driven) and dynamic manga scripts (dialogue/storyboard-driven) through AI-guided workflows.

**Architecture:** Unified tree-node data model (`ScriptProject` → `ScriptNode`) with an AI session state machine (`ScriptSession`) driving a multi-phase workflow: concept → Q&A → outline → expand. Completely independent from the novel module with its own routes (`/api/v1/drama/`), views (`/drama/`), store, and AI service.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/SQLite, Vue 3 + Pinia + Element Plus + Tiptap, SSE streaming for AI generation.

**Spec:** `docs/superpowers/specs/2026-03-25-drama-script-generator-design.md`

---

## Task 1: Backend Models — ScriptProject, ScriptNode, ScriptSession

**Files:**
- Create: `backend/app/models/script_project.py`
- Create: `backend/app/models/script_node.py`
- Create: `backend/app/models/script_session.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_drama_models.py`

- [ ] **Step 1: Write test for ScriptProject model creation**

```python
# backend/tests/test_drama_models.py
import pytest
from sqlalchemy import select
from app.models.script_project import ScriptProject


@pytest.mark.asyncio
async def test_create_script_project(test_db, test_user):
    """ScriptProject can be created with required fields."""
    project = ScriptProject(
        user_id=test_user.id,
        title="测试剧本",
        script_type="explanatory",
        concept="一个妈妈用榴莲教训熊孩子",
        status="drafting",
    )
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    assert project.id is not None
    assert project.script_type == "explanatory"
    assert project.status == "drafting"
    assert project.ai_config is None
    assert project.created_at is not None


@pytest.mark.asyncio
async def test_create_script_node_tree(test_db, test_user):
    """ScriptNode supports tree structure with parent_id."""
    project = ScriptProject(
        user_id=test_user.id,
        title="动态漫测试",
        script_type="dynamic",
        concept="皇子觉醒",
        status="drafting",
    )
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    from app.models.script_node import ScriptNode

    episode = ScriptNode(
        project_id=project.id,
        node_type="episode",
        title="第1集",
        sort_order=0,
    )
    test_db.add(episode)
    await test_db.commit()
    await test_db.refresh(episode)

    scene = ScriptNode(
        project_id=project.id,
        parent_id=episode.id,
        node_type="scene",
        title="01-1 京城大学堂 日/内",
        sort_order=0,
    )
    test_db.add(scene)
    await test_db.commit()

    result = await test_db.execute(
        select(ScriptNode).where(ScriptNode.parent_id == episode.id)
    )
    children = result.scalars().all()
    assert len(children) == 1
    assert children[0].node_type == "scene"


@pytest.mark.asyncio
async def test_cascade_delete_project_deletes_nodes(test_db, test_user):
    """Deleting a project cascades to nodes and session."""
    project = ScriptProject(
        user_id=test_user.id,
        title="删除测试",
        script_type="explanatory",
        concept="测试",
        status="drafting",
    )
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    from app.models.script_node import ScriptNode

    node = ScriptNode(
        project_id=project.id,
        node_type="section",
        title="1",
        sort_order=0,
    )
    test_db.add(node)
    await test_db.commit()

    project_id = project.id
    await test_db.delete(project)
    await test_db.commit()

    result = await test_db.execute(
        select(ScriptNode).where(ScriptNode.project_id == project_id)
    )
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_script_session_unique_per_project(test_db, test_user):
    """Only one ScriptSession per project (unique constraint)."""
    from app.models.script_session import ScriptSession

    project = ScriptProject(
        user_id=test_user.id,
        title="会话测试",
        script_type="dynamic",
        concept="测试",
        status="drafting",
    )
    test_db.add(project)
    await test_db.commit()
    await test_db.refresh(project)

    session1 = ScriptSession(
        project_id=project.id,
        state="init",
    )
    test_db.add(session1)
    await test_db.commit()

    session2 = ScriptSession(
        project_id=project.id,
        state="questioning",
    )
    test_db.add(session2)

    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await test_db.commit()
    await test_db.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_models.py -v`
Expected: FAIL — modules not found

- [ ] **Step 3: Create ScriptProject model**

```python
# backend/app/models/script_project.py
"""
剧本项目模型
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Integer, String, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScriptProject(Base):
    __tablename__ = "script_projects"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属用户",
    )
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, comment="剧本标题"
    )
    script_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="剧本类型: explanatory(解说漫) / dynamic(动态漫)",
    )
    concept: Mapped[str] = mapped_column(
        Text, nullable=False, comment="一句话故事概念"
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="drafting",
        comment="创作阶段: drafting/outlined/writing/completed",
    )
    ai_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="独立AI配置(provider/model/temperature/prompts)"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="扩展元数据(风格/受众/预计集数等)",
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # Relationships
    nodes: Mapped[List["ScriptNode"]] = relationship(
        "ScriptNode",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ScriptNode.sort_order",
    )
    session: Mapped[Optional["ScriptSession"]] = relationship(
        "ScriptSession",
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    owner: Mapped["User"] = relationship("User", backref="script_projects")
```

- [ ] **Step 4: Create ScriptNode model**

```python
# backend/app/models/script_node.py
"""
剧本节点模型 - 树形结构
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, Integer, String, Text, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScriptNode(Base):
    __tablename__ = "script_nodes"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("script_projects.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属剧本项目",
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("script_nodes.id", ondelete="CASCADE"),
        nullable=True,
        comment="父节点ID，NULL为根节点",
    )
    node_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="节点类型: episode/scene/dialogue/action/effect/inner_voice/section/narration/intro",
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="节点标题"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="文本内容"
    )
    speaker: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="说话人(仅dialogue类型)"
    )
    visual_desc: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="画面描述(仅动态漫action/effect)"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="同级排序序号"
    )
    is_completed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="内容是否已完成"
    )
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="扩展字段(角色外貌/特效说明等)",
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # Relationships
    project: Mapped["ScriptProject"] = relationship(
        "ScriptProject", back_populates="nodes"
    )
    children: Mapped[List["ScriptNode"]] = relationship(
        "ScriptNode",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="ScriptNode.sort_order",
    )
    parent: Mapped[Optional["ScriptNode"]] = relationship(
        "ScriptNode",
        back_populates="children",
        remote_side=[id],
    )
```

- [ ] **Step 5: Create ScriptSession model**

```python
# backend/app/models/script_session.py
"""
AI引导会话模型
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScriptSession(Base):
    __tablename__ = "script_sessions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    project_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("script_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="关联剧本项目(一对一)",
    )
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="init",
        comment="当前阶段: init/questioning/outlining/expanding/completed",
    )
    history: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
        comment="问答历史[{role, content}]，最大30轮",
    )
    outline_draft: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="大纲草稿JSON"
    )
    current_node_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("script_nodes.id", ondelete="SET NULL"),
        nullable=True,
        comment="当前扩写节点",
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # Relationships
    project: Mapped["ScriptProject"] = relationship(
        "ScriptProject", back_populates="session"
    )
```

- [ ] **Step 6: Register models in `__init__.py`**

Modify `backend/app/models/__init__.py` — add imports:

```python
from app.models.script_project import ScriptProject
from app.models.script_node import ScriptNode
from app.models.script_session import ScriptSession
```

Add to `__all__`:
```python
__all__ = [
    # ... existing ...
    "ScriptProject", "ScriptNode", "ScriptSession"
]
```

- [ ] **Step 7: Run tests**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_models.py -v`
Expected: All 4 tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/script_project.py backend/app/models/script_node.py backend/app/models/script_session.py backend/app/models/__init__.py backend/tests/test_drama_models.py
git commit -m "feat(drama): add ScriptProject, ScriptNode, ScriptSession models"
```

---

## Task 2: Database Migration Script

**Files:**
- Create: `backend/scripts/migrate_add_drama.py`

- [ ] **Step 1: Create migration script**

```python
# backend/scripts/migrate_add_drama.py
"""
数据库迁移脚本：创建剧本模块表
- script_projects
- script_nodes
- script_sessions
"""
import asyncio
from sqlalchemy import text
from app.core.database import engine

# Import models to ensure they're registered with Base.metadata
import app.models  # noqa: F401


async def migrate():
    """Create drama script tables if they don't exist."""
    async with engine.begin() as conn:
        # Check if tables already exist
        if "sqlite" in str(engine.url):
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='script_projects'")
            )
        else:
            result = await conn.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_name='script_projects'")
            )

        if result.fetchone():
            print("Drama tables already exist, skipping.")
            return

        print("Creating drama script tables...")

        # Use Base.metadata to create only our new tables
        from app.core.database import Base
        from app.models.script_project import ScriptProject  # noqa: F401
        from app.models.script_node import ScriptNode  # noqa: F401
        from app.models.script_session import ScriptSession  # noqa: F401

        tables = [
            Base.metadata.tables["script_projects"],
            Base.metadata.tables["script_nodes"],
            Base.metadata.tables["script_sessions"],
        ]
        await conn.run_sync(
            lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables)
        )

        print("Migration completed: script_projects, script_nodes, script_sessions created.")


if __name__ == "__main__":
    asyncio.run(migrate())
```

- [ ] **Step 2: Run migration**

Run: `cd /data/project/novel-writer && python -m backend.scripts.migrate_add_drama`
Expected: "Creating drama script tables..." → "Migration completed..."

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/migrate_add_drama.py
git commit -m "chore(drama): add database migration script for drama tables"
```

---

## Task 3: Backend Schemas

**Files:**
- Create: `backend/app/schemas/drama.py`
- Test: `backend/tests/test_drama_schemas.py`

- [ ] **Step 1: Write test for schema validation**

```python
# backend/tests/test_drama_schemas.py
import pytest
from app.schemas.drama import (
    ScriptProjectCreate,
    ScriptNodeCreate,
    SessionAnswerRequest,
    GlobalDirectiveRequest,
)


def test_project_create_valid():
    data = ScriptProjectCreate(
        title="测试剧本",
        script_type="explanatory",
        concept="一个妈妈用榴莲教训熊孩子",
    )
    assert data.title == "测试剧本"
    assert data.status == "drafting"


def test_project_create_invalid_type():
    with pytest.raises(ValueError):
        ScriptProjectCreate(
            title="测试",
            script_type="invalid_type",
            concept="测试",
        )


def test_node_create_valid():
    node = ScriptNodeCreate(
        node_type="episode",
        title="第1集",
        sort_order=0,
    )
    assert node.parent_id is None


def test_session_answer():
    answer = SessionAnswerRequest(content="东方玄幻")
    assert answer.content == "东方玄幻"


def test_global_directive_valid():
    directive = GlobalDirectiveRequest(
        instruction="节奏太慢，压缩到15集",
        scope="outline",
    )
    assert directive.node_ids is None


def test_global_directive_with_nodes():
    directive = GlobalDirectiveRequest(
        instruction="对话更口语化",
        scope="selected_nodes",
        node_ids=[1, 2, 3],
    )
    assert len(directive.node_ids) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_schemas.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Create schemas**

```python
# backend/app/schemas/drama.py
"""
剧本模块 Pydantic Schemas
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── ScriptProject ──

VALID_SCRIPT_TYPES = Literal["explanatory", "dynamic"]
VALID_STATUSES = Literal["drafting", "outlined", "writing", "completed"]


class AIPromptConfig(BaseModel):
    """用户可编辑的提示词模板"""
    questioning: Optional[str] = None
    outlining: Optional[str] = None
    expanding: Optional[str] = None
    rewriting: Optional[str] = None


class AIConfig(BaseModel):
    """独立AI配置（不含API Key）"""
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    prompts: Optional[AIPromptConfig] = None


class ScriptProjectCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    script_type: VALID_SCRIPT_TYPES
    concept: str = Field(..., min_length=1, max_length=5000)
    status: VALID_STATUSES = "drafting"
    ai_config: Optional[AIConfig] = None
    metadata: Optional[dict] = None


class ScriptProjectUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    concept: Optional[str] = Field(None, max_length=5000)
    status: Optional[VALID_STATUSES] = None
    metadata: Optional[dict] = None


class AIConfigUpdate(BaseModel):
    """更新AI配置（含提示词模板）"""
    provider: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, ge=1, le=32000)
    prompts: Optional[AIPromptConfig] = None


class ScriptProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    script_type: str
    concept: str
    status: str
    ai_config: Optional[dict] = None
    metadata_: Optional[dict] = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: Optional[datetime] = None


class ScriptProjectListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    script_type: str
    concept: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── ScriptNode ──

VALID_NODE_TYPES = Literal[
    "episode", "scene", "dialogue", "action", "effect", "inner_voice",
    "section", "narration", "intro",
]

EXPLANATORY_NODE_TYPES = {"intro", "section", "narration"}
DYNAMIC_NODE_TYPES = {"episode", "scene", "dialogue", "action", "effect", "inner_voice"}


class ScriptNodeCreate(BaseModel):
    parent_id: Optional[int] = None
    node_type: VALID_NODE_TYPES
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    speaker: Optional[str] = Field(None, max_length=100)
    visual_desc: Optional[str] = None
    sort_order: int = 0
    metadata: Optional[dict] = None


class ScriptNodeUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    speaker: Optional[str] = Field(None, max_length=100)
    visual_desc: Optional[str] = None
    sort_order: Optional[int] = None
    is_completed: Optional[bool] = None
    metadata: Optional[dict] = None


class ScriptNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    parent_id: Optional[int] = None
    node_type: str
    title: Optional[str] = None
    content: Optional[str] = None
    speaker: Optional[str] = None
    visual_desc: Optional[str] = None
    sort_order: int
    is_completed: bool
    metadata_: Optional[dict] = Field(None, alias="metadata_")
    created_at: datetime
    updated_at: Optional[datetime] = None


class ScriptNodeTreeResponse(ScriptNodeResponse):
    """节点+子节点的树形响应"""
    children: List["ScriptNodeTreeResponse"] = []


class ReorderRequest(BaseModel):
    """批量重排序请求"""
    orders: List[dict] = Field(
        ..., description="[{id: int, sort_order: int, parent_id: int|null}]"
    )


# ── ScriptSession ──

class SessionAnswerRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class ScriptSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    state: str
    history: Optional[list] = None
    outline_draft: Optional[dict] = None
    current_node_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


# ── AI Operations ──

class ExpandNodeRequest(BaseModel):
    """扩写节点请求"""
    instruction: Optional[str] = Field(None, max_length=2000, description="额外指令")


class RewriteRequest(BaseModel):
    """重写选中内容"""
    content: str = Field(..., min_length=1, max_length=50000)
    instruction: str = Field(..., min_length=1, max_length=2000)
    node_id: Optional[int] = None


class GlobalDirectiveRequest(BaseModel):
    """全局指令"""
    instruction: str = Field(..., min_length=1, max_length=5000)
    scope: Literal["outline", "all_nodes", "selected_nodes"]
    node_ids: Optional[List[int]] = None
```

- [ ] **Step 4: Run tests**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_schemas.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/drama.py backend/tests/test_drama_schemas.py
git commit -m "feat(drama): add Pydantic schemas for drama module"
```

---

## Task 4: Backend Router — Project CRUD + Node CRUD

**Files:**
- Create: `backend/app/routers/drama.py`
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/middleware/request_logging.py`
- Test: `backend/tests/test_drama_api.py`

- [ ] **Step 1: Write test for project CRUD API**

```python
# backend/tests/test_drama_api.py
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_create_drama_project(auth_headers):
    """POST /api/v1/drama/ creates a project."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/api/v1/drama/",
            json={
                "title": "榴莲惩罚",
                "script_type": "explanatory",
                "concept": "一个妈妈用榴莲教训熊孩子",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 201
    data = resp.json()
    assert data["title"] == "榴莲惩罚"
    assert data["script_type"] == "explanatory"


@pytest.mark.asyncio
async def test_list_drama_projects(auth_headers):
    """GET /api/v1/drama/ returns user's projects."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create one first
        await client.post(
            "/api/v1/drama/",
            json={
                "title": "测试列表",
                "script_type": "dynamic",
                "concept": "皇子觉醒",
            },
            headers=auth_headers,
        )
        resp = await client.get("/api/v1/drama/", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_create_node(auth_headers):
    """POST /api/v1/drama/{id}/nodes creates a node."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        proj = await client.post(
            "/api/v1/drama/",
            json={
                "title": "节点测试",
                "script_type": "dynamic",
                "concept": "测试",
            },
            headers=auth_headers,
        )
        project_id = proj.json()["id"]

        resp = await client.post(
            f"/api/v1/drama/{project_id}/nodes",
            json={
                "node_type": "episode",
                "title": "第1集",
                "sort_order": 0,
            },
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.json()["node_type"] == "episode"


@pytest.mark.asyncio
async def test_node_type_validation(auth_headers):
    """Creating wrong node_type for script_type returns 400."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        proj = await client.post(
            "/api/v1/drama/",
            json={
                "title": "校验测试",
                "script_type": "explanatory",
                "concept": "测试",
            },
            headers=auth_headers,
        )
        project_id = proj.json()["id"]

        # episode is dynamic-only, should fail for explanatory
        resp = await client.post(
            f"/api/v1/drama/{project_id}/nodes",
            json={
                "node_type": "episode",
                "title": "第1集",
            },
            headers=auth_headers,
        )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_api.py -v`
Expected: FAIL — router not found

- [ ] **Step 3: Create drama router**

```python
# backend/app/routers/drama.py
"""
剧本模块路由
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.models.script_project import ScriptProject
from app.models.script_node import ScriptNode
from app.models.script_session import ScriptSession
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.drama import (
    ScriptProjectCreate,
    ScriptProjectUpdate,
    ScriptProjectResponse,
    ScriptProjectListResponse,
    AIConfigUpdate,
    ScriptNodeCreate,
    ScriptNodeUpdate,
    ScriptNodeResponse,
    ScriptNodeTreeResponse,
    ReorderRequest,
    SessionAnswerRequest,
    ScriptSessionResponse,
    ExpandNodeRequest,
    RewriteRequest,
    GlobalDirectiveRequest,
    EXPLANATORY_NODE_TYPES,
    DYNAMIC_NODE_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/drama", tags=["drama"])


# ── Helper: get project with ownership check ──

async def get_drama_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScriptProject:
    result = await db.execute(
        select(ScriptProject).where(
            ScriptProject.id == id,
            or_(
                ScriptProject.user_id == current_user.id,
                current_user.is_superuser == True,
            ),
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="剧本不存在或无权访问")
    return project


# ── Project CRUD ──

@router.post("/", response_model=ScriptProjectResponse, status_code=201)
async def create_project(
    payload: ScriptProjectCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建剧本项目"""
    project = ScriptProject(
        user_id=current_user.id,
        title=payload.title,
        script_type=payload.script_type,
        concept=payload.concept,
        status=payload.status,
        ai_config=payload.ai_config.model_dump() if payload.ai_config else None,
        metadata_=payload.metadata,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/", response_model=List[ScriptProjectListResponse])
async def list_projects(
    script_type: Optional[str] = Query(None, description="按类型筛选"),
    status: Optional[str] = Query(None, description="按状态筛选"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取用户剧本列表"""
    stmt = (
        select(ScriptProject)
        .where(ScriptProject.user_id == current_user.id)
        .order_by(ScriptProject.created_at.desc())
    )
    if script_type:
        stmt = stmt.where(ScriptProject.script_type == script_type)
    if status:
        stmt = stmt.where(ScriptProject.status == status)
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/{id}", response_model=ScriptProjectResponse)
async def get_project(
    project: ScriptProject = Depends(get_drama_project),
):
    """获取剧本详情"""
    return project


@router.put("/{id}", response_model=ScriptProjectResponse)
async def update_project(
    payload: ScriptProjectUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新剧本信息"""
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "metadata":
            setattr(project, "metadata_", value)
        else:
            setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/{id}", status_code=204)
async def delete_project(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除剧本（级联删除节点和会话）"""
    await db.delete(project)
    await db.commit()


@router.put("/{id}/ai-config", response_model=ScriptProjectResponse)
async def update_ai_config(
    payload: AIConfigUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新AI配置（含提示词模板）"""
    config = project.ai_config or {}
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "prompts" and value is not None:
            config["prompts"] = value if isinstance(value, dict) else value.model_dump()
        else:
            config[field] = value
    project.ai_config = config
    await db.commit()
    await db.refresh(project)
    return project


# ── Node CRUD ──

def _validate_node_type(script_type: str, node_type: str):
    """校验 node_type 与 script_type 的匹配关系"""
    if script_type == "explanatory" and node_type not in EXPLANATORY_NODE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"解说漫剧本不支持 '{node_type}' 类型节点",
        )
    if script_type == "dynamic" and node_type not in DYNAMIC_NODE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"动态漫剧本不支持 '{node_type}' 类型节点",
        )


@router.get("/{id}/nodes", response_model=List[ScriptNodeTreeResponse])
async def get_nodes(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """获取所有节点（树形结构）"""
    result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = result.scalars().all()

    # Build tree
    node_map = {n.id: {**ScriptNodeResponse.model_validate(n).model_dump(), "children": []} for n in all_nodes}
    roots = []
    for n in all_nodes:
        node_dict = node_map[n.id]
        if n.parent_id and n.parent_id in node_map:
            node_map[n.parent_id]["children"].append(node_dict)
        else:
            roots.append(node_dict)
    return roots


@router.post("/{id}/nodes", response_model=ScriptNodeResponse, status_code=201)
async def create_node(
    payload: ScriptNodeCreate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """创建节点"""
    _validate_node_type(project.script_type, payload.node_type)

    node = ScriptNode(
        project_id=project.id,
        parent_id=payload.parent_id,
        node_type=payload.node_type,
        title=payload.title,
        content=payload.content,
        speaker=payload.speaker,
        visual_desc=payload.visual_desc,
        sort_order=payload.sort_order,
        metadata_=payload.metadata,
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


@router.put("/{id}/nodes/{node_id}", response_model=ScriptNodeResponse)
async def update_node(
    node_id: int,
    payload: ScriptNodeUpdate,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """更新节点"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "metadata":
            setattr(node, "metadata_", value)
        else:
            setattr(node, field, value)
    await db.commit()
    await db.refresh(node)
    return node


@router.delete("/{id}/nodes/{node_id}", status_code=204)
async def delete_node(
    node_id: int,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除节点（级联删除子节点）"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    await db.delete(node)
    await db.commit()


@router.put("/{id}/nodes/reorder")
async def reorder_nodes(
    payload: ReorderRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """批量重排序节点"""
    for item in payload.orders:
        result = await db.execute(
            select(ScriptNode).where(
                ScriptNode.id == item["id"],
                ScriptNode.project_id == project.id,
            )
        )
        node = result.scalar_one_or_none()
        if node:
            node.sort_order = item["sort_order"]
            if "parent_id" in item:
                node.parent_id = item["parent_id"]
    await db.commit()
    return {"ok": True}


# ── Session CRUD ──

@router.post("/{id}/session", response_model=ScriptSessionResponse)
async def get_or_create_session(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """获取或创建引导会话（幂等）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if session:
        return session

    session = ScriptSession(
        project_id=project.id,
        state="init",
        history=[],
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.delete("/{id}/session", status_code=204)
async def delete_session(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """删除当前会话（用于重新开始问答）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if session:
        await db.delete(session)
        await db.commit()
```

- [ ] **Step 4: Register router in `__init__.py` and `main.py`**

In `backend/app/routers/__init__.py`, add:
```python
from app.routers.drama import router as drama_router
```

In `backend/app/main.py`, add:
```python
from app.routers import drama_router
# ...
app.include_router(drama_router)
```

- [ ] **Step 5: Update SSE middleware whitelist**

In `backend/app/middleware/request_logging.py`, update:
```python
SSE_PATH_KEYWORDS = ["/ai/generate", "/ai/batch-generate", "/drama/"]
```

- [ ] **Step 6: Run tests**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/test_drama_api.py -v`
Expected: All 4 tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/drama.py backend/app/routers/__init__.py backend/app/main.py backend/app/middleware/request_logging.py backend/tests/test_drama_api.py
git commit -m "feat(drama): add drama router with project/node/session CRUD"
```

---

## Task 5: Backend — ScriptAIService

**Files:**
- Create: `backend/app/services/script_ai_service.py`

- [ ] **Step 1: Create ScriptAIService**

```python
# backend/app/services/script_ai_service.py
"""
剧本专用 AI 服务
独立于小说的 AIService，使用项目级别的 AI 配置和提示词模板
"""
import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 默认提示词模板 ──

DEFAULT_PROMPTS = {
    "explanatory": {
        "questioning": """你是一位专业的解说漫剧本策划师。解说漫以旁白叙述故事，类似有声小说/短视频解说的文本。
用户给出了一个故事概念，你需要通过提问来帮助他完善故事细节。

规则：
- 每次只问一个问题
- 可以提供参考选项，也可以让用户自由回答
- 关注：叙事视角、主要人物关系、情感基调、故事结构、反转点、高潮设计
- 根据已有回答动态决定下一个问题
- 当信息足够生成大纲时，设置 should_continue 为 false

故事概念：{concept}

历史对话：
{history}

请输出JSON格式：
{{"question": "你的问题", "options": ["选项A", "选项B", "选项C"], "should_continue": true, "reasoning": "内部推理"}}""",

        "outlining": """你是一位专业的解说漫剧本策划师。根据以下信息生成解说漫的结构化大纲。

解说漫结构：导语(intro) → 分段(section) → 旁白叙述(narration)

故事概念：{concept}
问答记录：{history}

请输出JSON格式的大纲：
{{"nodes": [{{"temp_id": "t1", "node_type": "intro", "title": "导语", "summary": "..."}}, {{"temp_id": "t2", "node_type": "section", "title": "1", "summary": "...", "children": []}}]}}""",

        "expanding": """你是一位专业的解说漫剧本作家。请根据大纲扩写以下段落。

解说漫特点：以旁白叙述，对话嵌入叙述中用引号标记，注重情感描写和心理活动。

故事概念：{concept}
当前节点：{node_title}
节点摘要：{node_summary}
前文内容：{prev_content}
后续摘要：{next_summary}

请直接输出扩写内容，不要包含JSON格式。""",

        "rewriting": """你是一位专业的解说漫剧本编辑。请根据以下指令重写内容。

原文：{content}
指令：{instruction}

请直接输出重写后的内容。""",
    },
    "dynamic": {
        "questioning": """你是一位专业的动态漫剧本策划师。动态漫以画面和对话展现故事，包含分镜描述、角色对话、特效标注。
用户给出了一个故事概念，你需要通过提问来帮助他完善故事细节。

规则：
- 每次只问一个问题
- 可以提供参考选项，也可以让用户自由回答
- 关注：主要角色+外貌描述、情感基调、预计集数、关键战斗/转折场景、世界观设定
- 根据已有回答动态决定下一个问题
- 当信息足够生成大纲时，设置 should_continue 为 false

故事概念：{concept}

历史对话：
{history}

请输出JSON格式：
{{"question": "你的问题", "options": ["选项A", "选项B", "选项C"], "should_continue": true, "reasoning": "内部推理"}}""",

        "outlining": """你是一位专业的动态漫剧本策划师。根据以下信息生成动态漫的结构化大纲。

动态漫结构：集(episode) → 场景(scene)，每个场景标注地点/时间/内外景

故事概念：{concept}
问答记录：{history}

请输出JSON格式的大纲：
{{"nodes": [{{"temp_id": "t1", "node_type": "episode", "title": "第1集", "summary": "...", "children": [{{"temp_id": "t1-1", "node_type": "scene", "title": "01-1 场景名 日/内", "summary": "..."}}]}}]}}""",

        "expanding": """你是一位专业的动态漫剧本作家。请根据大纲扩写以下场景。

动态漫格式规范：
- △ 标记画面动作描述
- 角色名：对话内容（角色对话）
- OS角色名：内心独白
- 【】标记特效/系统提示
- 角色首次出场需有外貌描述（角色名：性别/外貌+服装/气质）

故事概念：{concept}
当前节点：{node_title}
节点摘要：{node_summary}
前文内容：{prev_content}
后续摘要：{next_summary}

请直接输出扩写内容，不要包含JSON格式。""",

        "rewriting": """你是一位专业的动态漫剧本编辑。请根据以下指令重写内容。

原文：{content}
指令：{instruction}

请直接输出重写后的内容。""",
    },
}


class ScriptAIService:
    """剧本专用AI服务"""

    def __init__(self, project):
        self.project = project
        self.ai_config = project.ai_config or {}
        self.script_type = project.script_type

        # Resolve provider config
        self.provider = self.ai_config.get("provider", settings.DEFAULT_AI_PROVIDER)
        self.model = self.ai_config.get("model", self._default_model())
        self.temperature = self.ai_config.get("temperature", 0.8)
        self.max_tokens = self.ai_config.get("max_tokens", 4096)

    def _default_model(self) -> str:
        if self.provider == "openai":
            return settings.OPENAI_MODEL
        elif self.provider == "anthropic":
            return settings.ANTHROPIC_MODEL
        elif self.provider == "ollama":
            return settings.OLLAMA_MODEL
        return settings.OPENAI_MODEL

    def _get_prompt(self, stage: str, **kwargs) -> str:
        """获取提示词：优先用户自定义，否则默认模板"""
        user_prompts = self.ai_config.get("prompts", {})
        template = (
            user_prompts.get(stage)
            or DEFAULT_PROMPTS.get(self.script_type, {}).get(stage, "")
        )
        return template.format(**kwargs)

    async def _call_llm(self, prompt: str) -> AsyncGenerator[str, None]:
        """调用LLM，SSE流式输出"""
        if self.provider == "openai":
            async for chunk in self._call_openai(prompt):
                yield chunk
        elif self.provider == "anthropic":
            async for chunk in self._call_anthropic(prompt):
                yield chunk
        elif self.provider == "ollama":
            async for chunk in self._call_ollama(prompt):
                yield chunk
        else:
            async for chunk in self._call_openai(prompt):
                yield chunk

    async def _call_openai(self, prompt: str) -> AsyncGenerator[str, None]:
        """OpenAI compatible API call"""
        url = f"{settings.OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data)
                            content = chunk["choices"][0]["delta"].get("content", "")
                            if content:
                                yield content
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue

    async def _call_anthropic(self, prompt: str) -> AsyncGenerator[str, None]:
        """Anthropic API call"""
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": settings.ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data.get("type") == "content_block_delta":
                                text = data.get("delta", {}).get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue

    async def _call_ollama(self, prompt: str) -> AsyncGenerator[str, None]:
        """Ollama API call"""
        url = f"{settings.OLLAMA_BASE_URL}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            text = data.get("response", "")
                            if text:
                                yield text
                        except json.JSONDecodeError:
                            continue

    async def generate_question(self, concept: str, history: list) -> AsyncGenerator[str, None]:
        """动态生成下一个引导问题"""
        history_text = "\n".join(
            f"{'AI' if h['role'] == 'assistant' else '用户'}: {h['content']}"
            for h in (history or [])
        )
        prompt = self._get_prompt(
            "questioning", concept=concept, history=history_text
        )
        full_response = ""
        async for chunk in self._call_llm(prompt):
            full_response += chunk
            yield chunk

    async def generate_outline(self, concept: str, history: list) -> AsyncGenerator[str, None]:
        """生成结构化大纲"""
        history_text = "\n".join(
            f"{'AI' if h['role'] == 'assistant' else '用户'}: {h['content']}"
            for h in (history or [])
        )
        prompt = self._get_prompt(
            "outlining", concept=concept, history=history_text
        )
        async for chunk in self._call_llm(prompt):
            yield chunk

    async def expand_node(
        self,
        concept: str,
        node_title: str,
        node_summary: str,
        prev_content: str = "",
        next_summary: str = "",
        instruction: str = "",
    ) -> AsyncGenerator[str, None]:
        """扩写节点内容"""
        prompt = self._get_prompt(
            "expanding",
            concept=concept,
            node_title=node_title,
            node_summary=node_summary or "",
            prev_content=prev_content,
            next_summary=next_summary,
        )
        if instruction:
            prompt += f"\n\n额外要求：{instruction}"
        async for chunk in self._call_llm(prompt):
            yield chunk

    async def rewrite_content(
        self, content: str, instruction: str
    ) -> AsyncGenerator[str, None]:
        """重写选中内容"""
        prompt = self._get_prompt(
            "rewriting", content=content, instruction=instruction
        )
        async for chunk in self._call_llm(prompt):
            yield chunk

    async def global_directive(
        self, instruction: str, context: str
    ) -> AsyncGenerator[str, None]:
        """全局指令"""
        prompt = f"""你是一位专业的{
            '解说漫' if self.script_type == 'explanatory' else '动态漫'
        }剧本编辑。

用户对当前剧本提出了全局调整要求：
{instruction}

当前内容：
{context}

请根据要求输出调整后的内容。如果是大纲调整，请输出JSON格式的新大纲。如果是内容调整，请直接输出新内容。"""
        async for chunk in self._call_llm(prompt):
            yield chunk
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/script_ai_service.py
git commit -m "feat(drama): add ScriptAIService with provider-agnostic streaming"
```

---

## Task 6: Backend — AI Session & Generation Routes

**Files:**
- Modify: `backend/app/routers/drama.py` (append AI routes)

- [ ] **Step 1: Add AI routes to drama router**

Append to `backend/app/routers/drama.py`:

```python
from fastapi.responses import StreamingResponse
from app.services.script_ai_service import ScriptAIService

# ── AI Session Routes ──

@router.post("/{id}/session/answer")
async def session_answer(
    payload: SessionAnswerRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """提交回答，返回AI下一个问题（SSE）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    # Update history
    history = session.history or []
    history.append({"role": "user", "content": payload.content})

    # Check max rounds
    if len(history) >= 60:  # 30 rounds = 60 messages
        session.state = "outlining"
        session.history = history
        await db.commit()
        raise HTTPException(status_code=400, detail="已达最大提问轮数，请生成大纲")

    session.state = "questioning"
    session.history = history
    await db.commit()

    ai_service = ScriptAIService(project)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_question(
                project.concept, history
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"

            # Save AI response to history
            history.append({"role": "assistant", "content": full_response})
            session.history = history
            await db.commit()

            yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
        except Exception as e:
            logger.error(f"AI生成失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{id}/session/skip")
async def session_skip(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """跳过问答，进入大纲生成"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    session.state = "outlining"
    await db.commit()
    return {"ok": True, "state": "outlining"}


@router.post("/{id}/session/generate-outline")
async def session_generate_outline(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """生成大纲（SSE流式）"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")

    session.state = "outlining"
    await db.commit()

    ai_service = ScriptAIService(project)

    async def stream():
        full_response = ""
        try:
            async for chunk in ai_service.generate_outline(
                project.concept, session.history
            ):
                full_response += chunk
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"

            # Try to parse as JSON and save to outline_draft
            try:
                outline = json.loads(full_response)
                session.outline_draft = outline
            except json.JSONDecodeError:
                session.outline_draft = {"raw": full_response}
            await db.commit()

            yield f"data: {json.dumps({'done': True, 'outline': session.outline_draft})}\n\n"
        except Exception as e:
            logger.error(f"大纲生成失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{id}/session/confirm-outline")
async def session_confirm_outline(
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """确认大纲，将outline_draft写入ScriptNode"""
    result = await db.execute(
        select(ScriptSession).where(ScriptSession.project_id == project.id)
    )
    session = result.scalar_one_or_none()
    if not session or not session.outline_draft:
        raise HTTPException(status_code=400, detail="无大纲可确认")

    # Delete existing nodes
    await db.execute(
        select(ScriptNode).where(ScriptNode.project_id == project.id)
    )
    existing = (await db.execute(
        select(ScriptNode).where(ScriptNode.project_id == project.id)
    )).scalars().all()
    for node in existing:
        await db.delete(node)
    await db.flush()

    # Create nodes from outline_draft
    draft = session.outline_draft
    nodes_data = draft.get("nodes", [])

    async def create_nodes(items, parent_id=None, order_start=0):
        for i, item in enumerate(items):
            node = ScriptNode(
                project_id=project.id,
                parent_id=parent_id,
                node_type=item.get("node_type", "section"),
                title=item.get("title", ""),
                content=item.get("summary", ""),
                sort_order=order_start + i,
            )
            db.add(node)
            await db.flush()
            await db.refresh(node)

            children = item.get("children", [])
            if children:
                await create_nodes(children, parent_id=node.id)

    await create_nodes(nodes_data)

    session.state = "expanding"
    project.status = "outlined"
    await db.commit()

    return {"ok": True, "state": "expanding"}


# ── AI Content Generation Routes ──

@router.post("/{id}/nodes/{node_id}/expand")
async def expand_node(
    node_id: int,
    payload: ExpandNodeRequest = None,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """扩写节点（SSE）"""
    result = await db.execute(
        select(ScriptNode).where(
            ScriptNode.id == node_id,
            ScriptNode.project_id == project.id,
        )
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")

    # Get prev/next context
    siblings = (await db.execute(
        select(ScriptNode).where(
            ScriptNode.project_id == project.id,
            ScriptNode.parent_id == node.parent_id,
        ).order_by(ScriptNode.sort_order)
    )).scalars().all()

    prev_content = ""
    next_summary = ""
    for i, s in enumerate(siblings):
        if s.id == node.id:
            if i > 0 and siblings[i - 1].content:
                prev_content = siblings[i - 1].content[-500:]
            if i < len(siblings) - 1:
                next_summary = siblings[i + 1].title or ""
            break

    ai_service = ScriptAIService(project)

    async def stream():
        try:
            async for chunk in ai_service.expand_node(
                concept=project.concept,
                node_title=node.title or "",
                node_summary=node.content or "",
                prev_content=prev_content,
                next_summary=next_summary,
                instruction=payload.instruction if payload else "",
            ):
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"扩写失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{id}/ai/rewrite")
async def ai_rewrite(
    payload: RewriteRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """重写选中内容（SSE）"""
    ai_service = ScriptAIService(project)

    async def stream():
        try:
            async for chunk in ai_service.rewrite_content(
                content=payload.content,
                instruction=payload.instruction,
            ):
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"重写失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{id}/ai/global-directive")
async def ai_global_directive(
    payload: GlobalDirectiveRequest,
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """全局指令（SSE）"""
    # Build context based on scope
    if payload.scope == "outline":
        result = await db.execute(
            select(ScriptSession).where(ScriptSession.project_id == project.id)
        )
        session = result.scalar_one_or_none()
        context = json.dumps(session.outline_draft, ensure_ascii=False) if session and session.outline_draft else ""
    elif payload.scope == "selected_nodes" and payload.node_ids:
        result = await db.execute(
            select(ScriptNode).where(
                ScriptNode.id.in_(payload.node_ids),
                ScriptNode.project_id == project.id,
            ).order_by(ScriptNode.sort_order)
        )
        nodes = result.scalars().all()
        context = "\n\n".join(
            f"[{n.title}]\n{n.content or ''}" for n in nodes
        )
    else:  # all_nodes
        result = await db.execute(
            select(ScriptNode).where(
                ScriptNode.project_id == project.id
            ).order_by(ScriptNode.sort_order)
        )
        nodes = result.scalars().all()
        context = "\n\n".join(
            f"[{n.title}]\n{n.content or ''}" for n in nodes
        )

    ai_service = ScriptAIService(project)

    async def stream():
        try:
            async for chunk in ai_service.global_directive(
                instruction=payload.instruction,
                context=context,
            ):
                yield f"data: {json.dumps({'text': chunk, 'type': 'text'})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.error(f"全局指令失败: {e}", exc_info=True)
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── Export ──

@router.get("/{id}/export")
async def export_script(
    format: str = Query("txt", description="导出格式: txt/markdown"),
    project: ScriptProject = Depends(get_drama_project),
    db: AsyncSession = Depends(get_db),
):
    """导出剧本"""
    from fastapi.responses import PlainTextResponse

    result = await db.execute(
        select(ScriptNode)
        .where(ScriptNode.project_id == project.id)
        .order_by(ScriptNode.sort_order)
    )
    all_nodes = result.scalars().all()

    # Build tree
    node_map = {n.id: n for n in all_nodes}
    roots = [n for n in all_nodes if n.parent_id is None]

    lines = []
    if format == "markdown":
        lines.append(f"# {project.title}\n")
        lines.append(f"> {project.concept}\n")
    else:
        lines.append(project.title)
        lines.append(project.concept)
        lines.append("")

    def render_node(node, depth=0):
        prefix = "#" * (depth + 2) if format == "markdown" else ""
        if node.title:
            if format == "markdown":
                lines.append(f"{prefix} {node.title}\n")
            else:
                lines.append(f"{node.title}")
        if node.content:
            lines.append(node.content)
            lines.append("")

        children = sorted(
            [n for n in all_nodes if n.parent_id == node.id],
            key=lambda n: n.sort_order,
        )
        for child in children:
            render_node(child, depth + 1)

    for root in roots:
        render_node(root)

    content = "\n".join(lines)
    media_type = "text/markdown" if format == "markdown" else "text/plain"
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{project.title}.{"md" if format == "markdown" else "txt"}"'
        },
    )
```

Note: also add `import json` at the top of `drama.py` if not already present.

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/drama.py
git commit -m "feat(drama): add AI session, generation, and export routes"
```

---

## Task 7: Frontend — API Client + TypeScript Types

**Files:**
- Create: `frontend/src/api/drama.ts`

- [ ] **Step 1: Create API client**

```typescript
// frontend/src/api/drama.ts
import request from './request'
import { getAccessToken } from './request'

// ── Types ──

export interface AIPromptConfig {
  questioning?: string
  outlining?: string
  expanding?: string
  rewriting?: string
}

export interface AIConfig {
  provider?: string
  model?: string
  temperature?: number
  max_tokens?: number
  prompts?: AIPromptConfig
}

export interface ScriptProject {
  id: number
  user_id: number
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  status: 'drafting' | 'outlined' | 'writing' | 'completed'
  ai_config: AIConfig | null
  metadata_: Record<string, unknown> | null
  created_at: string
  updated_at: string | null
}

export interface ScriptProjectListItem {
  id: number
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  status: string
  created_at: string
  updated_at: string | null
}

export interface CreateScriptProjectData {
  title: string
  script_type: 'explanatory' | 'dynamic'
  concept: string
  ai_config?: AIConfig
  metadata?: Record<string, unknown>
}

export interface UpdateScriptProjectData {
  title?: string
  concept?: string
  status?: string
  metadata?: Record<string, unknown>
}

export interface ScriptNode {
  id: number
  project_id: number
  parent_id: number | null
  node_type: string
  title: string | null
  content: string | null
  speaker: string | null
  visual_desc: string | null
  sort_order: number
  is_completed: boolean
  metadata_: Record<string, unknown> | null
  created_at: string
  updated_at: string | null
  children?: ScriptNode[]
}

export interface CreateNodeData {
  parent_id?: number | null
  node_type: string
  title?: string
  content?: string
  speaker?: string
  visual_desc?: string
  sort_order?: number
  metadata?: Record<string, unknown>
}

export interface UpdateNodeData {
  title?: string
  content?: string
  speaker?: string
  visual_desc?: string
  sort_order?: number
  is_completed?: boolean
  metadata?: Record<string, unknown>
}

export interface ReorderItem {
  id: number
  sort_order: number
  parent_id?: number | null
}

export interface ScriptSession {
  id: number
  project_id: number
  state: 'init' | 'questioning' | 'outlining' | 'expanding' | 'completed'
  history: Array<{ role: string; content: string }> | null
  outline_draft: Record<string, unknown> | null
  current_node_id: number | null
  created_at: string
  updated_at: string | null
}

// ── Project API ──

export async function getDramaProjects(params?: {
  script_type?: string
  status?: string
  page?: number
  page_size?: number
}): Promise<ScriptProjectListItem[]> {
  return request.get<ScriptProjectListItem[]>('/drama/', { params })
}

export async function createDramaProject(
  data: CreateScriptProjectData,
): Promise<ScriptProject> {
  return request.post<ScriptProject>('/drama/', data)
}

export async function getDramaProject(id: number): Promise<ScriptProject> {
  return request.get<ScriptProject>(`/drama/${id}`)
}

export async function updateDramaProject(
  id: number,
  data: UpdateScriptProjectData,
): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}`, data)
}

export async function deleteDramaProject(id: number): Promise<void> {
  return request.delete(`/drama/${id}`)
}

export async function updateAIConfig(
  id: number,
  data: AIConfig,
): Promise<ScriptProject> {
  return request.put<ScriptProject>(`/drama/${id}/ai-config`, data)
}

// ── Node API ──

export async function getNodes(projectId: number): Promise<ScriptNode[]> {
  return request.get<ScriptNode[]>(`/drama/${projectId}/nodes`)
}

export async function createNode(
  projectId: number,
  data: CreateNodeData,
): Promise<ScriptNode> {
  return request.post<ScriptNode>(`/drama/${projectId}/nodes`, data)
}

export async function updateNode(
  projectId: number,
  nodeId: number,
  data: UpdateNodeData,
): Promise<ScriptNode> {
  return request.put<ScriptNode>(`/drama/${projectId}/nodes/${nodeId}`, data)
}

export async function deleteNode(
  projectId: number,
  nodeId: number,
): Promise<void> {
  return request.delete(`/drama/${projectId}/nodes/${nodeId}`)
}

export async function reorderNodes(
  projectId: number,
  orders: ReorderItem[],
): Promise<void> {
  return request.put(`/drama/${projectId}/nodes/reorder`, { orders })
}

// ── Session API ──

export async function getOrCreateSession(
  projectId: number,
): Promise<ScriptSession> {
  return request.post<ScriptSession>(`/drama/${projectId}/session`)
}

export async function deleteSession(projectId: number): Promise<void> {
  return request.delete(`/drama/${projectId}/session`)
}

export async function skipToOutline(
  projectId: number,
): Promise<{ ok: boolean }> {
  return request.post(`/drama/${projectId}/session/skip`)
}

export async function confirmOutline(
  projectId: number,
): Promise<{ ok: boolean }> {
  return request.post(`/drama/${projectId}/session/confirm-outline`)
}

// ── SSE Streaming ──

export function streamSessionAnswer(
  projectId: number,
  content: string,
  onChunk: (text: string) => void,
  onDone: (fullResponse?: string) => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/answer`,
    { content },
    onChunk,
    onDone,
    onError,
  )
}

export function streamGenerateOutline(
  projectId: number,
  onChunk: (text: string) => void,
  onDone: (outline?: Record<string, unknown>) => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/session/generate-outline`,
    {},
    onChunk,
    onDone,
    onError,
  )
}

export function streamExpandNode(
  projectId: number,
  nodeId: number,
  instruction?: string,
  onChunk?: (text: string) => void,
  onDone?: () => void,
  onError?: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/nodes/${nodeId}/expand`,
    instruction ? { instruction } : {},
    onChunk || (() => {}),
    onDone || (() => {}),
    onError || (() => {}),
  )
}

export function streamRewrite(
  projectId: number,
  data: { content: string; instruction: string; node_id?: number },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/ai/rewrite`,
    data,
    onChunk,
    onDone,
    onError,
  )
}

export function streamGlobalDirective(
  projectId: number,
  data: { instruction: string; scope: string; node_ids?: number[] },
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): AbortController {
  return _streamRequest(
    `/api/v1/drama/${projectId}/ai/global-directive`,
    data,
    onChunk,
    onDone,
    onError,
  )
}

// ── Export ──

export function getExportUrl(projectId: number, format: 'txt' | 'markdown'): string {
  return `/api/v1/drama/${projectId}/export?format=${format}`
}

// ── Internal SSE helper ──

function _streamRequest(
  url: string,
  body: Record<string, unknown>,
  onChunk: (text: string) => void,
  onDone: (data?: unknown) => void,
  onError: (error: string) => void,
): AbortController {
  const controller = new AbortController()
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: '请求失败' }))
        onError(err.detail || '请求失败')
        return
      }

      const reader = response.body?.getReader()
      if (!reader) {
        onError('无法读取响应流')
        return
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6))
              if (payload.text) onChunk(payload.text)
              if (payload.done) {
                onDone(payload.outline || payload.full_response)
                return
              }
              if (payload.error) {
                onError(payload.error)
                return
              }
            } catch {
              // ignore parse errors
            }
          }
        }
      }
      onDone()
    })
    .catch((err) => {
      if (err.name !== 'AbortError') {
        onError(err.message || '网络请求失败')
      }
    })

  return controller
}
```

Note: check if `getAccessToken` is already exported from `request.ts`. If not, you may need to extract the token logic. Check `frontend/src/api/ai.ts` for the existing pattern and match it.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/drama.ts
git commit -m "feat(drama): add frontend API client with SSE streaming"
```

---

## Task 8: Frontend — Pinia Store

**Files:**
- Create: `frontend/src/stores/drama.ts`

- [ ] **Step 1: Create drama store**

```typescript
// frontend/src/stores/drama.ts
import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  getDramaProjects,
  createDramaProject,
  getDramaProject,
  updateDramaProject,
  deleteDramaProject,
  updateAIConfig,
  getNodes,
  createNode,
  updateNode,
  deleteNode,
  reorderNodes,
  getOrCreateSession,
  deleteSession,
  confirmOutline,
} from '@/api/drama'
import type {
  ScriptProject,
  ScriptProjectListItem,
  CreateScriptProjectData,
  UpdateScriptProjectData,
  ScriptNode,
  CreateNodeData,
  UpdateNodeData,
  ReorderItem,
  ScriptSession,
  AIConfig,
} from '@/api/drama'

export const useDramaStore = defineStore('drama', () => {
  // State
  const projects = ref<ScriptProjectListItem[]>([])
  const currentProject = ref<ScriptProject | null>(null)
  const nodes = ref<ScriptNode[]>([])
  const currentNode = ref<ScriptNode | null>(null)
  const session = ref<ScriptSession | null>(null)
  const loading = ref(false)

  // ── Project Actions ──

  async function fetchProjects(params?: {
    script_type?: string
    status?: string
  }) {
    loading.value = true
    try {
      projects.value = await getDramaProjects(params)
    } finally {
      loading.value = false
    }
  }

  async function fetchProject(id: number) {
    loading.value = true
    try {
      currentProject.value = await getDramaProject(id)
    } finally {
      loading.value = false
    }
  }

  async function createProject(data: CreateScriptProjectData) {
    const project = await createDramaProject(data)
    projects.value.unshift({
      id: project.id,
      title: project.title,
      script_type: project.script_type,
      concept: project.concept,
      status: project.status,
      created_at: project.created_at,
      updated_at: project.updated_at,
    })
    return project
  }

  async function updateProject(id: number, data: UpdateScriptProjectData) {
    const updated = await updateDramaProject(id, data)
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  async function removeProject(id: number) {
    await deleteDramaProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
    if (currentProject.value?.id === id) {
      currentProject.value = null
    }
  }

  async function updateProjectAIConfig(id: number, config: AIConfig) {
    const updated = await updateAIConfig(id, config)
    if (currentProject.value?.id === id) {
      currentProject.value = updated
    }
    return updated
  }

  // ── Node Actions ──

  async function fetchNodes(projectId: number) {
    nodes.value = await getNodes(projectId)
  }

  async function addNode(projectId: number, data: CreateNodeData) {
    const node = await createNode(projectId, data)
    await fetchNodes(projectId)
    return node
  }

  async function editNode(projectId: number, nodeId: number, data: UpdateNodeData) {
    const updated = await updateNode(projectId, nodeId, data)
    if (currentNode.value?.id === nodeId) {
      currentNode.value = updated
    }
    await fetchNodes(projectId)
    return updated
  }

  async function removeNode(projectId: number, nodeId: number) {
    await deleteNode(projectId, nodeId)
    if (currentNode.value?.id === nodeId) {
      currentNode.value = null
    }
    await fetchNodes(projectId)
  }

  async function reorder(projectId: number, orders: ReorderItem[]) {
    await reorderNodes(projectId, orders)
    await fetchNodes(projectId)
  }

  function selectNode(node: ScriptNode | null) {
    currentNode.value = node
  }

  // ── Session Actions ──

  async function fetchSession(projectId: number) {
    session.value = await getOrCreateSession(projectId)
  }

  async function resetSession(projectId: number) {
    await deleteSession(projectId)
    session.value = null
  }

  async function confirmProjectOutline(projectId: number) {
    await confirmOutline(projectId)
    session.value = null
    await fetchNodes(projectId)
  }

  return {
    projects,
    currentProject,
    nodes,
    currentNode,
    session,
    loading,
    fetchProjects,
    fetchProject,
    createProject,
    updateProject,
    removeProject,
    updateProjectAIConfig,
    fetchNodes,
    addNode,
    editNode,
    removeNode,
    reorder,
    selectNode,
    fetchSession,
    resetSession,
    confirmProjectOutline,
  }
})
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/drama.ts
git commit -m "feat(drama): add Pinia store for drama module"
```

---

## Task 9: Frontend — Router Registration

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: Add drama routes**

Add these routes **before** the catch-all `/:pathMatch(.*)*` route in `frontend/src/router/index.ts`:

```typescript
{
  path: '/drama',
  name: 'DramaList',
  component: () => import('@/views/DramaListView.vue'),
  meta: { title: '我的剧本', requiresAuth: true },
},
{
  path: '/drama/create',
  name: 'DramaCreate',
  component: () => import('@/views/DramaCreateView.vue'),
  meta: { title: '创建剧本', requiresAuth: true },
},
{
  path: '/drama/wizard/:id',
  name: 'DramaWizard',
  component: () => import('@/views/DramaWizardView.vue'),
  meta: { title: 'AI剧本引导', requiresAuth: true },
},
{
  path: '/drama/workbench/:id',
  name: 'DramaWorkbench',
  component: () => import('@/views/DramaWorkbenchView.vue'),
  meta: { title: '剧本工作台', requiresAuth: true },
},
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/index.ts
git commit -m "feat(drama): register frontend routes for drama module"
```

---

## Task 10: Frontend — DramaListView

**Files:**
- Create: `frontend/src/views/DramaListView.vue`

- [ ] **Step 1: Create list view**

Create `frontend/src/views/DramaListView.vue` with:
- Card grid layout for script projects
- Type filter tabs (全部/解说漫/动态漫)
- Each card shows: title, type tag, concept preview, status tag, created date
- "新建剧本" button linking to `/drama/create`
- Card click navigates to wizard (if drafting) or workbench (if outlined+)
- Delete with confirmation
- Follow `ProjectListView.vue` styling patterns

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/DramaListView.vue
git commit -m "feat(drama): add DramaListView with project cards"
```

---

## Task 11: Frontend — DramaCreateView

**Files:**
- Create: `frontend/src/views/DramaCreateView.vue`

- [ ] **Step 1: Create create view**

Create `frontend/src/views/DramaCreateView.vue` with:
- Step 1: Two large selection cards for type (解说漫 / 动态漫) with descriptions
- Step 2: Concept textarea with placeholder examples
- Step 3: Expandable AI config panel (provider/model/temperature)
- Submit creates project and navigates to `/drama/wizard/:id`
- Use Element Plus `el-steps`, `el-card`, `el-input`, `el-select`, `el-slider`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/DramaCreateView.vue
git commit -m "feat(drama): add DramaCreateView with type selection and concept input"
```

---

## Task 12: Frontend — DramaWizardView

**Files:**
- Create: `frontend/src/views/DramaWizardView.vue`
- Create: `frontend/src/components/drama/WizardChat.vue`

- [ ] **Step 1: Create WizardChat component**

Create `frontend/src/components/drama/WizardChat.vue` with:
- Chat message list (AI left, user right)
- AI messages show question text + option buttons
- User can click an option or type custom answer
- Input area at bottom with send button
- SSE streaming for AI responses
- Parse AI JSON response to extract question/options/should_continue
- Auto-scroll to latest message

- [ ] **Step 2: Create DramaWizardView**

Create `frontend/src/views/DramaWizardView.vue` with:
- Top progress bar showing current state
- WizardChat component as main content
- "跳过，直接生成大纲" button at bottom
- When outline generated: show editable tree view of outline_draft
- Tree supports: rename, delete, add node, drag to reorder
- "确认大纲，开始创作" button to confirm and navigate to workbench

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/DramaWizardView.vue frontend/src/components/drama/WizardChat.vue
git commit -m "feat(drama): add DramaWizardView with AI-guided chat and outline editor"
```

---

## Task 13: Frontend — DramaWorkbenchView + Components

**Files:**
- Create: `frontend/src/views/DramaWorkbenchView.vue`
- Create: `frontend/src/components/drama/ScriptOutlineTree.vue`
- Create: `frontend/src/components/drama/ScriptEditor.vue`
- Create: `frontend/src/components/drama/ScriptAiPanel.vue`
- Create: `frontend/src/components/drama/GlobalDirectiveDialog.vue`
- Create: `frontend/src/components/drama/AiConfigPanel.vue`
- Create: `frontend/src/components/drama/NodeTypeIcon.vue`

- [ ] **Step 1: Create NodeTypeIcon component**

Small utility component that renders an icon per node_type. Use Element Plus icons.

- [ ] **Step 2: Create ScriptOutlineTree component**

Left panel tree view:
- Render nodes as tree using Element Plus `el-tree`
- Custom node content with NodeTypeIcon + title + completion checkbox
- Drag-and-drop reordering
- Right-click context menu: rename, delete, add child, AI regenerate
- Click selects node and loads content in editor
- "+" button to add new root node

- [ ] **Step 3: Create ScriptEditor component**

Center panel editor:
- Tiptap-based rich text editor
- Load selected node content
- Auto-save on content change (debounced)
- Dynamic manga: custom styling for △, OS, 【】, character names
- Explanatory manga: clean prose styling
- Text selection triggers AI rewrite option

- [ ] **Step 4: Create ScriptAiPanel component**

Right panel:
- Shows current node context
- Action buttons: "扩写本节点", "重写选中文本", "风格转换", "添加对话", "添加动作描述"
- Each action triggers SSE streaming
- Streaming output preview area
- "应用到编辑器" button to accept AI output

- [ ] **Step 5: Create GlobalDirectiveDialog component**

Dialog popup:
- Instruction textarea
- Scope radio group: "大纲" / "全部节点" / "选中节点"
- Node multi-select (shown when scope = "选中节点")
- Submit streams global directive

- [ ] **Step 6: Create AiConfigPanel component**

Drawer panel:
- Provider select, model input, temperature slider
- Prompt template editors (one textarea per stage)
- "恢复默认" button per prompt
- Save updates ai_config via API

- [ ] **Step 7: Create DramaWorkbenchView**

Main layout:
- Header: back button, title, type tag, "全局指令" button, export dropdown, AI config button
- Three-column layout with DraggableDivider (reuse from existing WorkbenchView)
- Left: ScriptOutlineTree
- Center: ScriptEditor
- Right: ScriptAiPanel (collapsible)
- Footer: node count, completion progress, word count

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/DramaWorkbenchView.vue frontend/src/components/drama/
git commit -m "feat(drama): add workbench view with outline tree, editor, and AI panel"
```

---

## Task 14: Integration Testing & Polish

**Files:**
- Modify: Various files for bug fixes

- [ ] **Step 1: Run backend tests**

Run: `cd /data/project/novel-writer && python -m pytest backend/tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run database migration**

Run: `cd /data/project/novel-writer && python -m backend.scripts.migrate_add_drama`

- [ ] **Step 3: Start backend and test API manually**

Run: `cd /data/project/novel-writer && python -m uvicorn app.main:app --reload --port 8083`
Test: `curl http://localhost:8083/api/v1/drama/ -H "Authorization: Bearer <token>"`

- [ ] **Step 4: Start frontend and verify routing**

Run: `cd /data/project/novel-writer/frontend && npm run dev`
Test: Navigate to `/drama`, `/drama/create`

- [ ] **Step 5: End-to-end flow test**

Test the full flow:
1. Create a new drama project (explanatory type)
2. Go through AI wizard Q&A
3. Generate and confirm outline
4. Expand a node in workbench
5. Use global directive
6. Export as TXT

- [ ] **Step 6: Fix any issues found**

- [ ] **Step 7: Final commit**

```bash
git add -A
git commit -m "fix(drama): integration fixes and polish"
```
