# Prose Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新建独立 `prose` 模块，将现有 ScriptProject 按场次并发改写为知乎严选风格散文，前端提供列表/创建/详情三页。

**Architecture:** 后端新增 `ProseProject` + `ProseScene` ORM，`prose_pipeline.run()` 三步编排（FETCH → SEARCH → REWRITE），`prose_event_bus` 做 SSE 推送；前端三个独立 View，遵守禁止左右分屏规范。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 (async) + SQLite(test)/PostgreSQL(prod)，Vue 3 + Element Plus，`AsyncMock` for unit tests。

---

## 文件映射

### 新建
| 文件 | 职责 |
|---|---|
| `backend/app/models/prose_project.py` | ProseProject + ProseScene ORM 实体 |
| `backend/app/schemas/prose.py` | Pydantic request/response schemas |
| `backend/app/services/prose_event_bus.py` | SSE project-level 事件总线 |
| `backend/app/services/prose_pipeline.py` | 三步 pipeline 编排 |
| `backend/app/routers/prose.py` | 5 个 API 端点 |
| `backend/tests/test_prose_models.py` | ORM 单元测试 |
| `backend/tests/test_prose_pipeline.py` | pipeline 单元测试（mock LLM + mock search） |
| `backend/tests/test_prose_router.py` | router 单元测试（TestClient） |
| `frontend/src/api/prose.ts` | 前端 API 客户端 |
| `frontend/src/views/ProseListView.vue` | 列表页 |
| `frontend/src/views/ProseCreateView.vue` | 创建页 |
| `frontend/src/views/ProseDetailView.vue` | 详情页 |

### 修改
| 文件 | 改动 |
|---|---|
| `backend/app/models/__init__.py` | import ProseProject, ProseScene |
| `backend/app/routers/__init__.py` | import + export prose_router |
| `backend/app/main.py` | include prose_router |
| `backend/app/services/style_sample_indexer.py` | 添加 `search_style_samples()` |
| `frontend/src/router/index.ts` | 添加 3 条 prose 路由 |
| `frontend/src/views/ProjectListView.vue` | 添加"散文改写"导航按钮 |

---

## Task 1: ORM 模型

**Files:**
- Create: `backend/app/models/prose_project.py`
- Test: `backend/tests/test_prose_models.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_prose_models.py
import pytest
from sqlalchemy import select
from app.models.prose_project import ProseProject, ProseScene
from app.models.user import User


@pytest.fixture
async def test_user(db_session):
    u = User(username="prose_tester", email="prose@test.com", hashed_password="x")
    db_session.add(u)
    await db_session.commit()
    await db_session.refresh(u)
    return u


@pytest.mark.asyncio
async def test_create_prose_project_minimal(db_session, test_user):
    p = ProseProject(
        user_id=test_user.id,
        title="测试散文",
        script_project_id=99,
        premise="一个都市爱情故事",
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    assert p.id > 0
    assert p.status == "pending"
    assert p.total_scenes == 0
    assert p.done_scenes == 0
    assert p.failed_scenes == 0


@pytest.mark.asyncio
async def test_scene_cascade_delete(db_session, test_user):
    p = ProseProject(
        user_id=test_user.id, title="x", script_project_id=1, premise="p"
    )
    db_session.add(p)
    await db_session.flush()
    s = ProseScene(
        project_id=p.id,
        scene_index=0,
        scene_title="场1",
        original_scene_text="原文",
    )
    db_session.add(s)
    await db_session.commit()

    await db_session.delete(p)
    await db_session.commit()

    remaining = (await db_session.execute(
        select(ProseScene).where(ProseScene.project_id == p.id)
    )).scalars().all()
    assert remaining == []
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_models.py -v 2>&1 | tail -10
```
预期：`ImportError: cannot import name 'ProseProject'`

- [ ] **Step 3: 创建 ORM 模型文件**

```python
# backend/app/models/prose_project.py
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class ProseProject(Base):
    __tablename__ = "prose_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    script_project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    script_project_title: Mapped[Optional[str]] = mapped_column(String(200))
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[Optional[str]] = mapped_column(String(50))
    style_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_scenes: Mapped[int] = mapped_column(Integer, default=0)
    done_scenes: Mapped[int] = mapped_column(Integer, default=0)
    failed_scenes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    scenes: Mapped[List["ProseScene"]] = relationship(
        "ProseScene",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProseScene.scene_index",
    )


class ProseScene(Base):
    __tablename__ = "prose_scenes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("prose_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_title: Mapped[str] = mapped_column(String(200), default="")
    original_scene_text: Mapped[str] = mapped_column(Text, nullable=False)
    prose_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    project: Mapped["ProseProject"] = relationship("ProseProject", back_populates="scenes")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_models.py -v 2>&1 | tail -10
```
预期：`2 passed`

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/models/prose_project.py backend/tests/test_prose_models.py
git commit -m "feat(prose): ProseProject + ProseScene ORM 模型 + 测试"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/prose.py`

- [ ] **Step 1: 创建 schemas 文件**

```python
# backend/app/schemas/prose.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ProseProjectCreate(BaseModel):
    script_project_id: int
    premise: str = Field(min_length=1, max_length=500)
    title: Optional[str] = None
    genre: Optional[str] = None


class ProseSceneOut(BaseModel):
    id: int
    scene_index: int
    scene_title: str
    original_scene_text: str
    prose_text: Optional[str]
    status: str
    error: Optional[str]
    token_used: int

    model_config = ConfigDict(from_attributes=True)


class ProseProjectOut(BaseModel):
    id: int
    user_id: int
    title: str
    script_project_id: int
    script_project_title: Optional[str]
    premise: str
    genre: Optional[str]
    style_snapshot: Optional[str]
    status: str
    total_scenes: int
    done_scenes: int
    failed_scenes: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ProseProjectDetail(ProseProjectOut):
    scenes: list[ProseSceneOut] = Field(default_factory=list)
```

- [ ] **Step 2: 验证 import 正常**

```bash
cd /data/project/novel-writer/backend && python3 -c "from app.schemas.prose import ProseProjectCreate, ProseProjectOut, ProseProjectDetail; print('OK')"
```
预期：`OK`

- [ ] **Step 3: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/schemas/prose.py
git commit -m "feat(prose): Pydantic schemas"
```

---

## Task 3: 基础服务 — prose_event_bus + search_style_samples

**Files:**
- Create: `backend/app/services/prose_event_bus.py`
- Modify: `backend/app/services/style_sample_indexer.py`

- [ ] **Step 1: 创建 prose_event_bus（复用 adaptation 模式，按 project_id 分组）**

```python
# backend/app/services/prose_event_bus.py
"""单进程内的 project 级事件总线，用于 prose SSE 推送。
与 adaptation_event_bus 相同模式，按 project_id 分组。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(eq=False)
class _Subscriber:
    project_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    _uid: int = field(default_factory=lambda: id(object()), repr=False)

    def __hash__(self) -> int:
        return self._uid

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Subscriber) and self._uid == other._uid


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, project_id: int) -> _Subscriber:
        sub = _Subscriber(project_id=project_id)
        self._subs.setdefault(project_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.project_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.project_id, None)

    async def publish(self, project_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(project_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


prose_event_bus = _EventBus()
```

- [ ] **Step 2: 在 style_sample_indexer.py 末尾添加 `search_style_samples()`**

在文件末尾（`_delete_chunks_only` 之后）追加：

```python
async def search_style_samples(
    session: AsyncSession,
    query_vec: list,
    top_k: int = 3,
    genre: Optional[str] = None,
) -> list[dict]:
    """内部检索：按 query_vec 找 top_k 样本的风格快照。
    供 prose_pipeline 直接调用（不走 HTTP）。

    返回：[{"sample_id": int, "title": str, "prompt_fragment": str, "prose_excerpt": str}]
    样本库为空或无向量时返回 []。
    """
    from sqlalchemy import text as _sql_text

    def _is_postgres() -> bool:
        from app.core.config import settings
        return not settings.DATABASE_URL.startswith("sqlite")

    if _is_postgres():
        sql = """
            SELECT c.sample_id,
                   1.0 - (c.embedding <=> CAST(:qv AS vector)) AS similarity
            FROM style_sample_chunks c
            JOIN style_samples s ON s.id = c.sample_id
            WHERE (:genre IS NULL OR s.genre = :genre)
              AND s.index_status = 'ready'
            ORDER BY c.embedding <=> CAST(:qv AS vector)
            LIMIT :lim
        """
        rows = (await session.execute(_sql_text(sql), {
            "qv": str(query_vec),
            "genre": genre,
            "lim": top_k * 5,
        })).all()
        sample_ids_ordered = list(dict.fromkeys(r.sample_id for r in rows))[:top_k]
    else:
        stmt = (
            select(StyleSampleChunk.sample_id)
            .join(StyleSample, StyleSample.id == StyleSampleChunk.sample_id)
            .where(StyleSample.index_status == "ready")
        )
        if genre:
            stmt = stmt.where(StyleSample.genre == genre)
        rows = (await session.execute(stmt)).all()
        sample_ids_ordered = list(dict.fromkeys(r.sample_id for r in rows))[:top_k]

    if not sample_ids_ordered:
        return []

    samples = (await session.execute(
        select(StyleSample).where(StyleSample.id.in_(sample_ids_ordered))
    )).scalars().all()
    by_id = {s.id: s for s in samples}

    result = []
    for sid in sample_ids_ordered:
        s = by_id.get(sid)
        if not s or not s.style_guide:
            continue
        import json as _json
        guide = _json.loads(s.style_guide)
        result.append({
            "sample_id": s.id,
            "title": s.title,
            "prompt_fragment": guide.get("prompt_fragment", ""),
            "prose_excerpt": guide.get("prose_excerpt", ""),
        })
    return result
```

同时在文件顶部的 imports 中确保 `Optional` 已导入（文件当前用 `List`，加上 `Optional`）：
```python
from typing import List, Optional
```

- [ ] **Step 3: 验证 import**

```bash
cd /data/project/novel-writer/backend && python3 -c "
from app.services.prose_event_bus import prose_event_bus
from app.services.style_sample_indexer import search_style_samples
print('OK')
"
```
预期：`OK`

- [ ] **Step 4: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/services/prose_event_bus.py backend/app/services/style_sample_indexer.py
git commit -m "feat(prose): prose_event_bus + search_style_samples 内部检索"
```

---

## Task 4: prose_pipeline 服务 + 测试

**Files:**
- Create: `backend/app/services/prose_pipeline.py`
- Create: `backend/tests/test_prose_pipeline.py`

- [ ] **Step 1: 写失败测试**

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_pipeline.py -v 2>&1 | tail -10
```
预期：`ImportError` 或 `ModuleNotFoundError`（prose_pipeline 未创建）

- [ ] **Step 3: 创建 prose_pipeline.py**

```python
# backend/app/services/prose_pipeline.py
"""散文生成三步 pipeline：FETCH_SCRIPT → SEARCH_STYLE → REWRITE。"""
import asyncio
import json
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.prose_project import ProseProject, ProseScene
from app.models.script_node import ScriptNode
from app.models.script_project import ScriptProject
from app.services.prose_event_bus import prose_event_bus
from app.services.style_sample_indexer import search_style_samples

logger = logging.getLogger(__name__)

PROSE_SYSTEM_HEADER = """你是一位专业的中文短篇小说作者，擅长知乎严选风格。
你的任务是将输入的剧本场景改写为连贯流畅的散文小说段落。
要求：保留原场景的核心情节与情感走向；风格完全遵照下方风格指南；
不要保留剧本格式（场景头、对白标记等）；直接输出散文正文，不加任何说明。"""

PROSE_REWRITE_CONCURRENCY = 3


class _LLMProvider:
    async def complete(self, prompt: str, **kwargs) -> str: ...


def _get_default_provider() -> _LLMProvider:
    from app.services.adaptation_llm_service import get_default_service
    return get_default_service().provider


async def _search_style_samples(
    session: AsyncSession, query_vec: list, top_k: int, genre: Optional[str]
) -> list[dict]:
    """薄包装，供测试 patch。"""
    return await search_style_samples(session, query_vec, top_k=top_k, genre=genre)


def _build_system_prompt(snapshot: list[dict]) -> str:
    parts = [PROSE_SYSTEM_HEADER]
    fragments = [s["prompt_fragment"] for s in snapshot if s.get("prompt_fragment")]
    if fragments:
        parts.append("\n\n".join(fragments))
    if snapshot and snapshot[0].get("prose_excerpt"):
        parts.append("# 参考段落\n" + snapshot[0]["prose_excerpt"])
    return "\n\n".join(parts)


async def run(
    session_factory: async_sessionmaker,
    project_id: int,
    provider: Optional[_LLMProvider] = None,
) -> None:
    """三步 pipeline 全流程。provider=None 时使用生产 LLM。"""
    if provider is None:
        provider = _get_default_provider()

    # ── Step 1: FETCH_SCRIPT ────────────────────────────────────────────────
    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one_or_none()
        if not project:
            logger.error("prose project %s not found", project_id)
            return

        nodes = (await session.execute(
            select(ScriptNode)
            .where(ScriptNode.project_id == project.script_project_id)
            .order_by(ScriptNode.sort_order)
        )).scalars().all()

        leaf_nodes = [n for n in nodes if n.content and n.content.strip()]

        if not leaf_nodes:
            project.status = "failed"
            project.style_snapshot = "[]"
            await session.commit()
            await prose_event_bus.publish(project_id, {"event": "project_failed"})
            return

        sp = (await session.execute(
            select(ScriptProject).where(ScriptProject.id == project.script_project_id)
        )).scalar_one_or_none()
        project.script_project_title = sp.title if sp else None
        project.total_scenes = len(leaf_nodes)
        project.status = "generating"

        for idx, node in enumerate(leaf_nodes):
            session.add(ProseScene(
                project_id=project_id,
                scene_index=idx,
                scene_title=node.title or f"场{idx + 1}",
                original_scene_text=node.content,
            ))
        await session.commit()
        premise = project.premise
        genre = project.genre

    # ── Step 2: SEARCH_STYLE ────────────────────────────────────────────────
    try:
        from app.services.embedding import embedding_service
        query_vec = await embedding_service.generate_embedding(premise)
        async with session_factory() as session:
            snapshot = await _search_style_samples(session, query_vec, top_k=3, genre=genre)
    except Exception as e:
        logger.warning("style sample search failed, degrading: %s", e)
        snapshot = []

    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one()
        project.style_snapshot = json.dumps(snapshot, ensure_ascii=False)
        await session.commit()

    system_prompt = _build_system_prompt(snapshot)

    # ── Step 3: REWRITE (concurrent) ─────────────────────────────────────────
    async with session_factory() as session:
        scenes = (await session.execute(
            select(ProseScene).where(ProseScene.project_id == project_id)
            .order_by(ProseScene.scene_index)
        )).scalars().all()
        scene_data = [
            (s.id, s.scene_index, s.scene_title, s.original_scene_text)
            for s in scenes
        ]

    sem = asyncio.Semaphore(PROSE_REWRITE_CONCURRENCY)

    async def _rewrite_one(scene_id: int, scene_index: int, title: str, original: str):
        async with sem:
            async with session_factory() as session:
                sc = (await session.execute(
                    select(ProseScene).where(ProseScene.id == scene_id)
                )).scalar_one()
                sc.status = "running"
                await session.commit()

            try:
                user_msg = f"将以下剧本场景改写为知乎严选风格短篇散文：\n{original}"
                prose = await provider.complete(user_msg, system=system_prompt)
                async with session_factory() as session:
                    sc = (await session.execute(
                        select(ProseScene).where(ProseScene.id == scene_id)
                    )).scalar_one()
                    sc.prose_text = prose
                    sc.status = "done"
                    await session.commit()
                await prose_event_bus.publish(project_id, {
                    "event": "scene_done",
                    "scene_index": scene_index,
                    "scene_title": title,
                    "status": "done",
                    "prose_text": prose,
                })
                return True
            except Exception as e:
                logger.exception("prose scene %s rewrite failed", scene_id)
                async with session_factory() as session:
                    sc = (await session.execute(
                        select(ProseScene).where(ProseScene.id == scene_id)
                    )).scalar_one()
                    sc.status = "failed"
                    sc.error = str(e)[:1000]
                    await session.commit()
                await prose_event_bus.publish(project_id, {
                    "event": "scene_done",
                    "scene_index": scene_index,
                    "scene_title": title,
                    "status": "failed",
                })
                return False

    results = await asyncio.gather(*[
        _rewrite_one(sid, sidx, stitle, sorig)
        for (sid, sidx, stitle, sorig) in scene_data
    ])

    done = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    if failed == 0:
        final_status = "done"
    elif done == 0:
        final_status = "failed"
    else:
        final_status = "partial"

    async with session_factory() as session:
        project = (await session.execute(
            select(ProseProject).where(ProseProject.id == project_id)
        )).scalar_one()
        project.status = final_status
        project.done_scenes = done
        project.failed_scenes = failed
        await session.commit()

    await prose_event_bus.publish(project_id, {
        "event": "project_done" if final_status == "done" else "project_failed",
        "status": final_status,
    })
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_pipeline.py -v 2>&1 | tail -15
```
预期：`4 passed`

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/services/prose_pipeline.py backend/tests/test_prose_pipeline.py
git commit -m "feat(prose): prose_pipeline 三步编排 + 测试（FETCH/SEARCH/REWRITE）"
```

---

## Task 5: prose router + 测试

**Files:**
- Create: `backend/app/routers/prose.py`
- Create: `backend/tests/test_prose_router.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_prose_router.py
"""prose router 测试 —— 全程 mock pipeline"""
import pytest
from unittest.mock import AsyncMock, patch

from app.models.prose_project import ProseProject, ProseScene
from app.models.script_project import ScriptProject
from app.models.user import User


@pytest.fixture
async def script_project(db_session, sample_user):
    sp = ScriptProject(
        user_id=sample_user.id, title="测试剧本", script_type="dynamic"
    )
    db_session.add(sp)
    await db_session.commit()
    await db_session.refresh(sp)
    return sp


@pytest.fixture
async def prose_project(db_session, sample_user, script_project):
    p = ProseProject(
        user_id=sample_user.id,
        title="测试散文项目",
        script_project_id=script_project.id,
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
async def test_create_prose_project_returns_pending(client, db_session, script_project):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post("/api/v1/prose", json={
            "script_project_id": script_project.id,
            "premise": "都市爱情故事",
            "title": "我的散文",
        })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["script_project_id"] == script_project.id
    assert body["premise"] == "都市爱情故事"


@pytest.mark.asyncio
async def test_create_returns_400_if_script_not_found(client):
    with patch("app.routers.prose.prose_pipeline.run", new=AsyncMock()):
        resp = client.post("/api/v1/prose", json={
            "script_project_id": 99999,
            "premise": "测试梗概",
        })
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_router.py -v 2>&1 | tail -10
```
预期：`ImportError` 或路由 404（router 未注册）

- [ ] **Step 3: 创建 prose router**

```python
# backend/app/routers/prose.py
"""散文生成模块路由：CRUD + SSE 5 个端点"""
import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.core.security import create_sse_ticket, verify_sse_ticket
from app.models.prose_project import ProseProject, ProseScene
from app.models.script_project import ScriptProject
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.prose import ProseProjectCreate, ProseProjectDetail, ProseProjectOut
from app.services import prose_pipeline
from app.services.prose_event_bus import prose_event_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/prose", tags=["prose"])


async def _get_owned_project(
    id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProseProject:
    p = (await db.execute(
        select(ProseProject).where(
            ProseProject.id == id,
            ProseProject.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "散文项目不存在或无权访问")
    return p


@router.post("", response_model=ProseProjectOut)
async def create_prose_project(
    payload: ProseProjectCreate,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sp = (await db.execute(
        select(ScriptProject).where(
            ScriptProject.id == payload.script_project_id,
            ScriptProject.user_id == current_user.id,
        )
    )).scalar_one_or_none()
    if not sp:
        raise HTTPException(400, "剧本不存在或无权访问")

    title = payload.title or f"《{sp.title}》散文改写"
    genre = payload.genre or getattr(sp, "genre", None)

    project = ProseProject(
        user_id=current_user.id,
        title=title,
        script_project_id=sp.id,
        script_project_title=sp.title,
        premise=payload.premise,
        genre=genre,
        status="pending",
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    background.add_task(prose_pipeline.run, async_session, project.id)
    return project


@router.get("", response_model=list[ProseProjectOut])
async def list_prose_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(ProseProject)
        .where(ProseProject.user_id == current_user.id)
        .order_by(ProseProject.created_at.desc())
    )).scalars().all()
    return rows


@router.get("/{id}", response_model=ProseProjectDetail)
async def get_prose_project(
    project: ProseProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    scenes = (await db.execute(
        select(ProseScene).where(ProseScene.project_id == project.id)
        .order_by(ProseScene.scene_index)
    )).scalars().all()
    out = ProseProjectDetail.model_validate(project)
    out.scenes = [s for s in scenes]
    return out


@router.delete("/{id}", status_code=204)
async def delete_prose_project(
    project: ProseProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(project)
    await db.commit()
    return Response(status_code=204)


@router.post("/{id}/stream/ticket")
async def create_stream_ticket(
    project: ProseProject = Depends(_get_owned_project),
    current_user: User = Depends(get_current_user),
):
    """颁发 30s 短票据，供 EventSource 拉 SSE 流"""
    return {"ticket": create_sse_ticket(current_user.id, project.id)}


@router.get("/{id}/stream")
async def stream_prose_project(id: int, ticket: str = Query(...)):
    if verify_sse_ticket(ticket, id) is None:
        raise HTTPException(401, "ticket 无效或已过期")
    sub = prose_event_bus.subscribe(id)

    async def gen():
        try:
            yield "data: " + json.dumps({"event": "subscribed", "project_id": id}) + "\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield "data: " + json.dumps(payload, default=str) + "\n\n"
                    if payload.get("event") in ("project_done", "project_failed"):
                        return
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            prose_event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_router.py -v 2>&1 | tail -15
```
预期：`6 passed`（注意此时 router 尚未注册到 main，TestClient 直接测通 `/api/v1/prose` 需要先完成 Task 6 注册）

- [ ] **Step 5: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/routers/prose.py backend/tests/test_prose_router.py
git commit -m "feat(prose): prose router 5 端点 + 测试"
```

---

## Task 6: 注册 model + router

**Files:**
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 修改 `backend/app/models/__init__.py`**

在文件末尾 `AdaptationSceneResult` 行后追加，并在 `__all__` 中添加：

```python
# 在现有 imports 末尾追加：
from app.models.prose_project import ProseProject, ProseScene

# 在 __all__ 列表末尾追加：
"ProseProject", "ProseScene",
```

- [ ] **Step 2: 修改 `backend/app/routers/__init__.py`**

追加一行 import 和一行 `__all__`：

```python
# 在文件末尾的 from ... 行之后追加：
from app.routers.prose import router as prose_router

# 在 __all__ 列表末尾追加：
"prose_router",
```

- [ ] **Step 3: 修改 `backend/app/main.py`**

在 `style_sample_router` 导入行之后添加 `prose_router`，并在 `app.include_router(style_sample_router)` 行之后添加：

```python
# imports 里添加：
    prose_router,

# include_router 里添加：
app.include_router(prose_router)
```

- [ ] **Step 4: 运行全部 router 测试确认通过**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/test_prose_router.py tests/test_prose_models.py tests/test_prose_pipeline.py -v 2>&1 | tail -20
```
预期：所有测试通过

- [ ] **Step 5: 运行全量测试确认无回归**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/ -q 2>&1 | tail -5
```
预期：所有已有测试通过，无新失败

- [ ] **Step 6: Commit**

```bash
cd /data/project/novel-writer && git add backend/app/models/__init__.py backend/app/routers/__init__.py backend/app/main.py
git commit -m "feat(prose): 注册 ProseProject 模型 + prose router 到 main"
```

---

## Task 7: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/prose.ts`

- [ ] **Step 1: 创建 prose.ts**

```typescript
// frontend/src/api/prose.ts
import { request } from './request'

export interface ProseProjectCreate {
  script_project_id: number
  premise: string
  title?: string
  genre?: string
}

export interface ProseSceneOut {
  id: number
  scene_index: number
  scene_title: string
  original_scene_text: string
  prose_text: string | null
  status: string
  error: string | null
  token_used: number
}

export interface ProseProjectOut {
  id: number
  user_id: number
  title: string
  script_project_id: number
  script_project_title: string | null
  premise: string
  genre: string | null
  style_snapshot: string | null
  status: string
  total_scenes: number
  done_scenes: number
  failed_scenes: number
  created_at: string
  updated_at: string | null
}

export interface ProseProjectDetail extends ProseProjectOut {
  scenes: ProseSceneOut[]
}

export const proseApi = {
  create(data: ProseProjectCreate) {
    return request.post<ProseProjectOut>('/api/v1/prose', data)
  },

  list() {
    return request.get<ProseProjectOut[]>('/api/v1/prose')
  },

  get(id: number) {
    return request.get<ProseProjectDetail>(`/api/v1/prose/${id}`)
  },

  delete(id: number) {
    return request.delete(`/api/v1/prose/${id}`)
  },

  getStreamTicket(id: number) {
    return request.post<{ ticket: string }>(`/api/v1/prose/${id}/stream/ticket`)
  },

  getStreamUrl(id: number, ticket: string): string {
    const base = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')
    return `${base}/api/v1/prose/${id}/stream?ticket=${ticket}`
  },
}
```

- [ ] **Step 2: 验证 TypeScript 编译无错**

```bash
cd /data/project/novel-writer/frontend && npx vue-tsc --noEmit 2>&1 | grep -i "prose" | head -10
```
预期：无输出（无错误）

- [ ] **Step 3: Commit**

```bash
cd /data/project/novel-writer && git add frontend/src/api/prose.ts
git commit -m "feat(prose): 前端 API 客户端 prose.ts"
```

---

## Task 8: 前端路由 + 导航入口

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/ProjectListView.vue`

- [ ] **Step 1: 在 `router/index.ts` 的 style-samples 路由之前插入三条 prose 路由**

在 `'/style-samples'` 路由对象之前插入：

```typescript
  {
    path: '/prose',
    name: 'ProseList',
    component: () => import('@/views/ProseListView.vue'),
    meta: { title: '散文改写', requiresAuth: true },
  },
  {
    path: '/prose/new',
    name: 'ProseCreate',
    component: () => import('@/views/ProseCreateView.vue'),
    meta: { title: '新建散文项目', requiresAuth: true },
  },
  {
    path: '/prose/:id',
    name: 'ProseDetail',
    component: () => import('@/views/ProseDetailView.vue'),
    meta: { title: '散文详情', requiresAuth: true },
  },
```

- [ ] **Step 2: 在 `ProjectListView.vue` 添加导航按钮**

在 `风格样本库` 按钮之前插入：

```html
<el-button @click="$router.push('/prose')" round>
  散文改写
</el-button>
```

- [ ] **Step 3: 验证 TypeScript 编译无错**

```bash
cd /data/project/novel-writer/frontend && npx vue-tsc --noEmit 2>&1 | grep -v "^$" | head -10
```
预期：无错误（ProseListView.vue 等文件不存在会有 warning，不是 error）

- [ ] **Step 4: Commit**

```bash
cd /data/project/novel-writer && git add frontend/src/router/index.ts frontend/src/views/ProjectListView.vue
git commit -m "feat(prose): 前端路由注册 + 主页导航入口"
```

---

## Task 9: 前端列表页 ProseListView.vue

**Files:**
- Create: `frontend/src/views/ProseListView.vue`

- [ ] **Step 1: 创建列表页**

```vue
<!-- frontend/src/views/ProseListView.vue -->
<template>
  <div style="padding: 24px">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px">
      <h2 style="margin: 0">散文改写</h2>
      <div>
        <el-button type="primary" @click="$router.push('/prose/new')">+ 新建散文项目</el-button>
        <el-button @click="loadList" style="margin-left: 8px">刷新</el-button>
      </div>
    </div>

    <el-table :data="projects" v-loading="loading" style="width: 100%">
      <el-table-column label="标题" prop="title" min-width="180" />
      <el-table-column label="来源剧本" prop="script_project_title" min-width="150">
        <template #default="{ row }">
          {{ row.script_project_title || `剧本 #${row.script_project_id}` }}
        </template>
      </el-table-column>
      <el-table-column label="进度" min-width="120">
        <template #default="{ row }">
          <span v-if="row.status === 'generating'">
            {{ row.done_scenes + row.failed_scenes }}/{{ row.total_scenes }}
          </span>
          <span v-else>{{ row.total_scenes }} 场</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" min-width="100">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">
            {{ statusLabel(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" min-width="160">
        <template #default="{ row }">
          {{ new Date(row.created_at).toLocaleString('zh-CN') }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="$router.push(`/prose/${row.id}`)">查看</el-button>
          <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ProseProjectOut } from '@/api/prose'
import { proseApi } from '@/api/prose'

const projects = ref<ProseProjectOut[]>([])
const loading = ref(false)

async function loadList() {
  loading.value = true
  try {
    const res = await proseApi.list()
    projects.value = res.data
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loading.value = false
  }
}

function statusTagType(status: string) {
  const map: Record<string, string> = {
    pending: 'info',
    generating: 'primary',
    done: 'success',
    partial: 'warning',
    failed: 'danger',
  }
  return map[status] ?? 'info'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    pending: '等待中',
    generating: '生成中',
    done: '完成',
    partial: '部分完成',
    failed: '失败',
  }
  return map[status] ?? status
}

async function handleDelete(row: ProseProjectOut) {
  await ElMessageBox.confirm(`确定删除「${row.title}」吗？`, '确认删除', {
    type: 'warning',
  })
  await proseApi.delete(row.id)
  ElMessage.success('已删除')
  await loadList()
}

onMounted(loadList)
</script>
```

- [ ] **Step 2: Commit**

```bash
cd /data/project/novel-writer && git add frontend/src/views/ProseListView.vue
git commit -m "feat(prose): 前端列表页 ProseListView"
```

---

## Task 10: 前端创建页 ProseCreateView.vue

**Files:**
- Create: `frontend/src/views/ProseCreateView.vue`

- [ ] **Step 1: 创建创建页**

```vue
<!-- frontend/src/views/ProseCreateView.vue -->
<template>
  <div style="padding: 24px; max-width: 640px; margin: 0 auto">
    <h2>新建散文改写项目</h2>

    <el-form :model="form" :rules="rules" ref="formRef" label-width="100px">
      <el-form-item label="来源剧本" prop="script_project_id">
        <el-select
          v-model="form.script_project_id"
          filterable
          placeholder="请选择剧本"
          style="width: 100%"
        >
          <el-option
            v-for="sp in scriptProjects"
            :key="sp.id"
            :label="sp.title"
            :value="sp.id"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="故事梗概" prop="premise">
        <el-input
          v-model="form.premise"
          type="textarea"
          :rows="3"
          placeholder="用一句话描述故事的核心，例如：都市白领因一次偶遇邂逅前任，重燃旧情"
        />
      </el-form-item>

      <el-form-item label="项目标题">
        <el-input v-model="form.title" placeholder="留空则自动生成" />
      </el-form-item>

      <el-form-item label="题材">
        <el-select v-model="form.genre" clearable placeholder="可选，留空自动继承剧本题材" style="width: 100%">
          <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="handleSubmit">
          开始改写
        </el-button>
        <el-button @click="$router.back()">取消</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { proseApi } from '@/api/prose'

const router = useRouter()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const form = reactive({
  script_project_id: null as number | null,
  premise: '',
  title: '',
  genre: '',
})

const rules = {
  script_project_id: [{ required: true, message: '请选择来源剧本', trigger: 'change' }],
  premise: [
    { required: true, message: '请输入故事梗概', trigger: 'blur' },
    { min: 5, max: 500, message: '梗概长度 5-500 字', trigger: 'blur' },
  ],
}

const genres = ['都市言情', '悬疑', '古风', '现实', '职场', '家庭', '其他']

interface ScriptProjectItem { id: number; title: string }
const scriptProjects = ref<ScriptProjectItem[]>([])

async function loadScriptProjects() {
  try {
    const { default: axios } = await import('axios')
    const token = localStorage.getItem('token')
    const res = await axios.get('/api/v1/drama', {
      headers: { Authorization: `Bearer ${token}` },
    })
    scriptProjects.value = res.data?.projects ?? res.data ?? []
  } catch {
    ElMessage.warning('无法加载剧本列表，请确认有已创建的剧本')
  }
}

async function handleSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    const res = await proseApi.create({
      script_project_id: form.script_project_id!,
      premise: form.premise,
      title: form.title || undefined,
      genre: form.genre || undefined,
    })
    ElMessage.success('项目已创建，正在生成中…')
    router.push(`/prose/${res.data.id}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail ?? '创建失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadScriptProjects)
</script>
```

- [ ] **Step 2: Commit**

```bash
cd /data/project/novel-writer && git add frontend/src/views/ProseCreateView.vue
git commit -m "feat(prose): 前端创建页 ProseCreateView"
```

---

## Task 11: 前端详情页 ProseDetailView.vue

**Files:**
- Create: `frontend/src/views/ProseDetailView.vue`

- [ ] **Step 1: 创建详情页**

```vue
<!-- frontend/src/views/ProseDetailView.vue -->
<template>
  <div style="padding: 24px">
    <!-- 项目信息头 -->
    <div v-if="project" style="margin-bottom: 16px">
      <div style="display: flex; justify-content: space-between; align-items: flex-start">
        <div>
          <h2 style="margin: 0 0 4px">{{ project.title }}</h2>
          <el-text type="info">
            来源：{{ project.script_project_title || `剧本 #${project.script_project_id}` }}
            ｜ 梗概：{{ project.premise }}
          </el-text>
        </div>
        <div style="display: flex; gap: 8px">
          <el-button
            v-if="project.status === 'done' || project.status === 'partial'"
            @click="exportTxt"
          >导出 TXT</el-button>
          <el-button @click="$router.push('/prose')">返回列表</el-button>
        </div>
      </div>

      <!-- 进度 -->
      <div style="margin-top: 12px">
        <el-tag :type="statusTagType(project.status)" style="margin-right: 8px">
          {{ statusLabel(project.status) }}
        </el-tag>
        <el-progress
          v-if="project.status === 'generating'"
          :percentage="progressPct"
          style="display: inline-flex; width: 300px; vertical-align: middle"
        />
        <el-text v-else type="info">
          {{ project.done_scenes }}/{{ project.total_scenes }} 场完成
          <span v-if="project.failed_scenes > 0" style="color: #f56c6c">
            ，{{ project.failed_scenes }} 场失败
          </span>
        </el-text>
      </div>

      <!-- 风格快照折叠 -->
      <el-collapse style="margin-top: 12px" v-if="styleSnapshot.length">
        <el-collapse-item title="风格样本快照" name="snapshot">
          <div v-for="s in styleSnapshot" :key="s.sample_id" style="margin-bottom: 12px">
            <strong>{{ s.title }}</strong>
            <div style="background: #f5f5f5; padding: 8px; border-radius: 4px; margin-top: 4px; font-size: 13px">
              {{ s.prompt_fragment }}
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <el-skeleton v-if="!project" :rows="5" animated />

    <!-- 场次列表 -->
    <el-collapse v-if="project" v-model="openScenes" accordion style="margin-top: 8px">
      <el-collapse-item
        v-for="scene in scenes"
        :key="scene.id"
        :name="scene.scene_index"
      >
        <template #title>
          <div style="display: flex; align-items: center; gap: 8px">
            <span>{{ scene.scene_title || `场 ${scene.scene_index + 1}` }}</span>
            <el-tag :type="sceneTagType(scene.status)" size="small">
              {{ sceneLabel(scene.status) }}
            </el-tag>
          </div>
        </template>

        <div v-if="scene.status === 'done' && scene.prose_text"
             style="white-space: pre-wrap; line-height: 1.8; padding: 8px">
          {{ scene.prose_text }}
        </div>
        <div v-else-if="scene.status === 'failed'"
             style="color: #f56c6c; padding: 8px">
          生成失败：{{ scene.error || '未知错误' }}
        </div>
        <div v-else style="color: #909399; padding: 8px">
          {{ scene.status === 'running' ? '生成中…' : '等待中' }}
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { ProseProjectDetail, ProseSceneOut } from '@/api/prose'
import { proseApi } from '@/api/prose'

const route = useRoute()
const projectId = Number(route.params.id)

const project = ref<ProseProjectDetail | null>(null)
const scenes = ref<ProseSceneOut[]>([])
const openScenes = ref<number[]>([])
let eventSource: EventSource | null = null

const styleSnapshot = computed(() => {
  if (!project.value?.style_snapshot) return []
  try {
    return JSON.parse(project.value.style_snapshot)
  } catch {
    return []
  }
})

const progressPct = computed(() => {
  if (!project.value || !project.value.total_scenes) return 0
  return Math.round(
    ((project.value.done_scenes + project.value.failed_scenes) / project.value.total_scenes) * 100
  )
})

function statusTagType(status: string) {
  const m: Record<string, string> = { pending: 'info', generating: 'primary', done: 'success', partial: 'warning', failed: 'danger' }
  return m[status] ?? 'info'
}

function statusLabel(status: string) {
  const m: Record<string, string> = { pending: '等待中', generating: '生成中', done: '完成', partial: '部分完成', failed: '失败' }
  return m[status] ?? status
}

function sceneTagType(status: string) {
  const m: Record<string, string> = { pending: 'info', running: 'primary', done: 'success', failed: 'danger' }
  return m[status] ?? 'info'
}

function sceneLabel(status: string) {
  const m: Record<string, string> = { pending: '等待', running: '生成中', done: '完成', failed: '失败' }
  return m[status] ?? status
}

async function loadDetail() {
  try {
    const res = await proseApi.get(projectId)
    project.value = res.data
    scenes.value = res.data.scenes
  } catch {
    ElMessage.error('加载失败')
  }
}

async function startSSE() {
  try {
    const ticketRes = await proseApi.getStreamTicket(projectId)
    const url = proseApi.getStreamUrl(projectId, ticketRes.data.ticket)
    eventSource = new EventSource(url)

    eventSource.onmessage = (e) => {
      const payload = JSON.parse(e.data)
      if (payload.event === 'scene_done') {
        const idx = scenes.value.findIndex(s => s.scene_index === payload.scene_index)
        if (idx >= 0) {
          scenes.value[idx] = {
            ...scenes.value[idx],
            status: payload.status,
            prose_text: payload.prose_text ?? null,
          }
        }
        if (project.value) {
          if (payload.status === 'done') project.value.done_scenes++
          else if (payload.status === 'failed') project.value.failed_scenes++
        }
      } else if (payload.event === 'project_done' || payload.event === 'project_failed') {
        if (project.value) project.value.status = payload.status === 'project_done' ? 'done' : payload.status
        eventSource?.close()
        eventSource = null
        loadDetail()
      }
    }
    eventSource.onerror = () => {
      eventSource?.close()
      eventSource = null
    }
  } catch {
    // SSE 失败降级为轮询
  }
}

function exportTxt() {
  const lines = scenes.value
    .filter(s => s.prose_text)
    .map(s => `## ${s.scene_title || `场 ${s.scene_index + 1}`}\n\n${s.prose_text}`)
    .join('\n\n---\n\n')
  const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `${project.value?.title ?? '散文'}.txt`
  a.click()
  URL.revokeObjectURL(a.href)
}

onMounted(async () => {
  await loadDetail()
  if (project.value?.status === 'generating' || project.value?.status === 'pending') {
    await startSSE()
  }
})

onBeforeUnmount(() => {
  eventSource?.close()
})
</script>
```

- [ ] **Step 2: 验证 TypeScript 编译无错**

```bash
cd /data/project/novel-writer/frontend && npx vue-tsc --noEmit 2>&1 | grep -i "prose" | head -10
```
预期：无输出

- [ ] **Step 3: 运行全量后端测试，确认无回归**

```bash
cd /data/project/novel-writer/backend && python3 -m pytest tests/ -q 2>&1 | tail -5
```
预期：所有测试通过

- [ ] **Step 4: Commit**

```bash
cd /data/project/novel-writer && git add frontend/src/views/ProseDetailView.vue
git commit -m "feat(prose): 前端详情页 ProseDetailView（SSE 进度 + 导出 TXT）"
```

---

## 自查结果

**Spec 覆盖检查：**
- ✅ ScriptProject 导入 → T4 FETCH_SCRIPT
- ✅ 自动检索 Top-3 → T4 SEARCH_STYLE + T3 search_style_samples
- ✅ 场级并发 SSE → T4 REWRITE + T5 SSE endpoints
- ✅ 详情页逐场展示 → T11
- ✅ 导出 TXT → T11 exportTxt()
- ✅ 5 个 API 端点 → T5
- ✅ 3 个前端页面 → T9/T10/T11
- ✅ DB migration 走 Base.metadata（create_all 自动，Alembic 生成见下）

**类型一致性：**
- `ProseScene.status` 枚举：pipeline (pending/running/done/failed) ↔ router test ↔ 前端 sceneTagType — 一致 ✅
- `ProseProject.status` 枚举：pending/generating/done/partial/failed — pipeline/router/frontend 一致 ✅
- `search_style_samples` 返回 `list[dict]` 键名：`sample_id/title/prompt_fragment/prose_excerpt` — pipeline 消费端一致 ✅

**Alembic migration 提示（手动步骤，非自动化）：**
如生产环境使用 Alembic，在 Task 6 完成后运行：
```bash
cd /data/project/novel-writer/backend && alembic revision --autogenerate -m "add_prose_tables" && alembic upgrade head
```
