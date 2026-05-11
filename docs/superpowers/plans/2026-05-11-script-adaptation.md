# 剧本改编系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地一个独立的「剧本改编」模块，导入剧本后按场切分→AI 抽实体→用户编辑映射→并发分场改写→场列表+diff+手改+多版本管理+导出。

**Architecture:** 4 张新表（`adaptation_*`），4 阶段流水线（PARSE/EXTRACT/SPLIT/REWRITE），FastAPI 路由 `/api/v1/adaptation`，asyncio.Semaphore 控并发，in-process pub/sub 推 SSE，Vue 3 三视图（List/Create/Workbench），与现有 ScriptProject 完全解耦。

**Tech Stack:** Python FastAPI + SQLAlchemy 2.0 (async) + PostgreSQL/SQLite + pgvector，Vue 3 + TypeScript + Vite + Element Plus，复用 `script_ai_service.get_provider()` 路由 LLM。

**Spec：** `docs/superpowers/specs/2026-05-11-script-adaptation-design.md`

**Spec 同步修正：** Spec §5 写的端点前缀是 `/api/adaptation`，与现有 `/api/v1/<module>` 约定不符；本 plan 使用 `/api/v1/adaptation`。

---

## Task 1：新增 4 张表的 SQLAlchemy 模型

**Files:**
- Create: `backend/app/models/adaptation_project.py`
- Create: `backend/app/models/adaptation_mapping_entry.py`
- Create: `backend/app/models/adaptation_version.py`
- Create: `backend/app/models/adaptation_scene_result.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_adaptation_models.py`

- [ ] **Step 1：先写最小失败测试**

```python
# backend/tests/test_adaptation_models.py
"""改编模块模型基础持久化测试。"""
import pytest
from sqlalchemy import select
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult


@pytest.mark.asyncio
async def test_adaptation_project_persist(test_db_session, test_user):
    """改编项目能写入并读回，metadata 默认 dict 可序列化。"""
    project = AdaptationProject(
        user_id=test_user.id,
        title="改编测试",
        source_text="原文一二三",
        intensity=2,
        status="ready",
        metadata_={"scene_boundaries": [{"index": 0, "start": 0, "end": 5, "title": "场1"}]},
    )
    test_db_session.add(project)
    await test_db_session.commit()

    found = (await test_db_session.execute(
        select(AdaptationProject).where(AdaptationProject.id == project.id)
    )).scalar_one()
    assert found.title == "改编测试"
    assert found.metadata_["scene_boundaries"][0]["title"] == "场1"


@pytest.mark.asyncio
async def test_adaptation_full_cascade(test_db_session, test_user):
    """version + scene_results + mapping 全套写入；删除项目级联清理。"""
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="ready")
    test_db_session.add(p); await test_db_session.flush()

    m = AdaptationMappingEntry(
        project_id=p.id, entity_type="person",
        original_text="李铁柱", replacement_text="马克", locked=True, order_index=0,
    )
    v = AdaptationVersion(
        project_id=p.id, version_no=1, triggered_by="full_run",
        status="running", mapping_snapshot=[{"original_text": "李铁柱", "replacement_text": "马克"}],
    )
    test_db_session.add_all([m, v]); await test_db_session.flush()

    s = AdaptationSceneResult(
        version_id=v.id, scene_index=0,
        original_scene_text="原文", scene_title="场1", status="pending",
    )
    test_db_session.add(s); await test_db_session.commit()

    pid = p.id
    await test_db_session.delete(p); await test_db_session.commit()
    remaining = (await test_db_session.execute(
        select(AdaptationVersion).where(AdaptationVersion.project_id == pid)
    )).scalars().all()
    assert remaining == []
```

- [ ] **Step 2：跑测试确认按预期失败**

```bash
cd backend && pytest tests/test_adaptation_models.py -v
```
Expected: ImportError（模型尚未创建）。

- [ ] **Step 3：写 `adaptation_project.py`**

```python
# backend/app/models/adaptation_project.py
"""改编项目模型。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationProject(Base):
    __tablename__ = "adaptation_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, comment="原文，写入后只读")
    intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False, default=2,
                                            comment="1=替换 2=润色 3=重铸")
    era_target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsing")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(),
                                                  onupdate=func.now())

    mappings = relationship(
        "AdaptationMappingEntry", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationMappingEntry.order_index",
    )
    versions = relationship(
        "AdaptationVersion", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationVersion.version_no",
    )
```

- [ ] **Step 4：写 `adaptation_mapping_entry.py`**

```python
# backend/app/models/adaptation_mapping_entry.py
"""改编模块的实体映射表。"""
from typing import Optional

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationMappingEntry(Base):
    __tablename__ = "adaptation_mapping_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="person/place/prop/era_term/other"
    )
    original_text: Mapped[str] = mapped_column(String(200), nullable=False)
    replacement_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project = relationship("AdaptationProject", back_populates="mappings")

    __table_args__ = (
        Index("ix_adaptation_mapping_proj_origin", "project_id", "original_text", unique=True),
    )
```

- [ ] **Step 5：写 `adaptation_version.py`**

```python
# backend/app/models/adaptation_version.py
"""改编版本（每次全场重跑产生一条）。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationVersion(Base):
    __tablename__ = "adaptation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="full_run")
    prompt_overrides: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mapping_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    project = relationship("AdaptationProject", back_populates="versions")
    scene_results = relationship(
        "AdaptationSceneResult", back_populates="version",
        cascade="all, delete-orphan", order_by="AdaptationSceneResult.scene_index",
    )
```

- [ ] **Step 6：写 `adaptation_scene_result.py`**

```python
# backend/app/models/adaptation_scene_result.py
"""改编单场结果。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, Float, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationSceneResult(Base):
    __tablename__ = "adaptation_scene_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_scene_text: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_scene_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scene_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_count_delta_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manual_edits: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    version = relationship("AdaptationVersion", back_populates="scene_results")

    __table_args__ = (
        UniqueConstraint("version_id", "scene_index", name="uq_adaptation_version_scene"),
    )
```

- [ ] **Step 7：注册到 `app/models/__init__.py`**

在 `from app.models.expansion_segment import ExpansionSegment` 之后追加：

```python
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
```

并在 `__all__` 列表追加这 4 个名字。

- [ ] **Step 8：跑测试**

```bash
cd backend && pytest tests/test_adaptation_models.py -v
```
Expected: PASS（建议先确认 conftest 提供 `test_db_session`、`test_user`，若名字不同则按 conftest 实际命名调整）。

- [ ] **Step 9：提交**

```bash
git add backend/app/models/adaptation_*.py backend/app/models/__init__.py backend/tests/test_adaptation_models.py
git commit -m "feat(adaptation): 新增 4 张改编模块表与基础持久化测试"
```

---

## Task 2：Pydantic schemas

**Files:**
- Create: `backend/app/schemas/adaptation.py`

- [ ] **Step 1：写 schemas，覆盖所有 API 出入参**

```python
# backend/app/schemas/adaptation.py
"""改编模块 Pydantic 出入参 schema。"""
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["person", "place", "prop", "era_term", "other"]


class AdaptationProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    raw_text: Optional[str] = None  # 粘贴入口；上传走 multipart 单独端点
    intent: Optional[str] = None
    intensity: int = Field(default=2, ge=1, le=3)
    era_target: Optional[str] = None


class AdaptationProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    intent: Optional[str] = None
    intensity: Optional[int] = Field(default=None, ge=1, le=3)
    era_target: Optional[str] = None


class MappingEntryIn(BaseModel):
    entity_type: EntityType
    original_text: str = Field(min_length=1, max_length=200)
    replacement_text: Optional[str] = Field(default=None, max_length=200)
    locked: bool = False
    notes: Optional[str] = None
    order_index: int = 0


class MappingEntryOut(MappingEntryIn):
    id: int


class MappingsBulkPut(BaseModel):
    entries: List[MappingEntryIn]


class SceneBoundary(BaseModel):
    index: int
    start: int
    end: int
    title: str


class AdaptationProjectOut(BaseModel):
    id: int
    title: str
    source_filename: Optional[str]
    intent: Optional[str]
    intensity: int
    era_target: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    word_count: int
    scene_boundaries: List[SceneBoundary] = []
    versions: List["AdaptationVersionOut"] = []
    mappings: List[MappingEntryOut] = []


class AdaptationVersionOut(BaseModel):
    id: int
    version_no: int
    triggered_by: str
    status: str
    stats: Optional[dict]
    error: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]


class SceneResultOut(BaseModel):
    id: int
    scene_index: int
    scene_title: Optional[str]
    status: str
    error: Optional[str]
    token_used: Optional[int]
    line_count_delta_pct: Optional[float]
    original_scene_text: str
    rewritten_scene_text: Optional[str]
    manual_edits: Optional[list] = []
    updated_at: datetime


class VersionDetailOut(AdaptationVersionOut):
    scene_results: List[SceneResultOut] = []


class RunCreate(BaseModel):
    extra_prompt: Optional[str] = None


class SceneRerunRequest(BaseModel):
    extra_prompt: Optional[str] = None


class SceneManualPatch(BaseModel):
    rewritten_scene_text: str = Field(min_length=0)


class MappingSuggestRequest(BaseModel):
    only_empty: bool = True  # 只补空，不覆盖已有 replacement
```

- [ ] **Step 2：sanity import**

```bash
cd backend && python -c "from app.schemas.adaptation import AdaptationProjectCreate; print('OK')"
```
Expected: `OK`

- [ ] **Step 3：提交**

```bash
git add backend/app/schemas/adaptation.py
git commit -m "feat(adaptation): 新增 schemas 定义"
```

---

## Task 3：配置项

**Files:**
- Modify: `backend/app/core/config.py`

- [ ] **Step 1：在 `Settings` 类内追加配置**

```python
# 改编模块配置
ADAPTATION_MAX_CHARS: int = 200_000
ADAPTATION_REWRITE_CONCURRENCY: int = 5
ADAPTATION_PER_SCENE_TIMEOUT_SEC: int = 90
ADAPTATION_EXTRACT_MODEL: str | None = None
ADAPTATION_REWRITE_MODEL: str | None = None
ADAPTATION_STALE_RUN_CLEANUP_AGE_SEC: int = 3600
```

- [ ] **Step 2：sanity**

```bash
cd backend && python -c "from app.core.config import settings; print(settings.ADAPTATION_MAX_CHARS)"
```
Expected: `200000`

- [ ] **Step 3：提交**

```bash
git add backend/app/core/config.py
git commit -m "feat(adaptation): 新增改编模块配置项"
```

---

## Task 4：场切分服务（纯函数，TDD）

**Files:**
- Create: `backend/app/services/adaptation_splitter.py`
- Test: `backend/tests/test_adaptation_splitter.py`

- [ ] **Step 1：写测试**

```python
# backend/tests/test_adaptation_splitter.py
"""场切分服务测试：仅测正则路径，LLM fallback 在 pipeline 测试中通过 mock 走。"""
import pytest
from app.services.adaptation_splitter import split_by_regex, SceneBoundary


def test_regex_chinese_scenes():
    text = "场1 长安城外\n李铁柱挥剑。\n场2 客栈\n二人对饮。"
    boundaries = split_by_regex(text)
    assert len(boundaries) == 2
    assert boundaries[0].title.startswith("场1")
    assert text[boundaries[0].start:boundaries[0].end].startswith("场1")
    assert text[boundaries[1].start:boundaries[1].end].startswith("场2")


def test_regex_int_ext_scenes():
    text = "INT. CAFE - DAY\nMark sips coffee.\nEXT. STREET - NIGHT\nRain falls."
    boundaries = split_by_regex(text)
    assert len(boundaries) == 2
    assert boundaries[0].title.startswith("INT.")


def test_regex_too_few_returns_empty():
    text = "场1 仅一场\n剩下都是正文"
    assert split_by_regex(text) == []


def test_regex_no_match_returns_empty():
    assert split_by_regex("毫无场标记的散文") == []


def test_boundaries_cover_text_continuously():
    text = "场1 a\n111\n场2 b\n222\n场3 c\n333"
    bs = split_by_regex(text)
    assert len(bs) == 3
    assert bs[0].start == 0
    assert bs[-1].end == len(text)
    for prev, nxt in zip(bs, bs[1:]):
        assert prev.end == nxt.start
```

- [ ] **Step 2：跑测试确认失败**

```bash
cd backend && pytest tests/test_adaptation_splitter.py -v
```
Expected: ImportError

- [ ] **Step 3：实现**

```python
# backend/app/services/adaptation_splitter.py
"""按场切分剧本文本。

正则优先：命中 ≥2 处场标记则用正则；否则返回空列表，调用方走 LLM fallback。
不在此模块直接调用 LLM，便于单测。
"""
import re
from dataclasses import dataclass
from typing import List

_PATTERNS = [
    re.compile(r"^\s*场\s*\d+", re.MULTILINE),
    re.compile(r"^\s*第[一二三四五六七八九十百千\d]+场", re.MULTILINE),
    re.compile(r"^\s*INT\.|^\s*EXT\.", re.MULTILINE),
    re.compile(r"^\s*\d+\.\s*[内外]景", re.MULTILINE),
]


@dataclass
class SceneBoundary:
    index: int
    start: int
    end: int
    title: str


def _collect_match_starts(text: str) -> list[int]:
    """收集所有匹配的起点偏移，去重并排序。"""
    starts: set[int] = set()
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            starts.add(m.start())
    return sorted(starts)


def _title_at(text: str, start: int) -> str:
    """从 start 取一行作为场标题（剥首尾空白，截断到 80 字）。"""
    end_of_line = text.find("\n", start)
    if end_of_line == -1:
        end_of_line = len(text)
    return text[start:end_of_line].strip()[:80]


def split_by_regex(text: str) -> List[SceneBoundary]:
    """按正则切场。命中 <2 返回空列表。"""
    starts = _collect_match_starts(text)
    if len(starts) < 2:
        return []
    boundaries: list[SceneBoundary] = []
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(text)
        boundaries.append(
            SceneBoundary(index=i, start=s, end=e, title=_title_at(text, s))
        )
    return boundaries
```

- [ ] **Step 4：跑测试确认通过**

```bash
cd backend && pytest tests/test_adaptation_splitter.py -v
```
Expected: 5 PASS

- [ ] **Step 5：提交**

```bash
git add backend/app/services/adaptation_splitter.py backend/tests/test_adaptation_splitter.py
git commit -m "feat(adaptation): 场切分服务（正则路径，含单测）"
```

---

## Task 5：In-process pub/sub for SSE（小工具）

**Files:**
- Create: `backend/app/services/adaptation_event_bus.py`
- Test: `backend/tests/test_adaptation_event_bus.py`

- [ ] **Step 1：写测试**

```python
# backend/tests/test_adaptation_event_bus.py
import asyncio
import pytest
from app.services.adaptation_event_bus import event_bus


@pytest.mark.asyncio
async def test_subscribe_receives_published_events():
    sub = event_bus.subscribe(version_id=42)
    try:
        async def publish_later():
            await asyncio.sleep(0.01)
            await event_bus.publish(42, {"event": "scene_done", "scene_index": 0})
            await event_bus.publish(43, {"event": "ignored"})
            await event_bus.publish(42, {"event": "done"})

        task = asyncio.create_task(publish_later())
        msgs: list = []
        async with asyncio.timeout(1.0):
            while len(msgs) < 2:
                msgs.append(await sub.queue.get())
        await task
        assert msgs[0]["event"] == "scene_done"
        assert msgs[1]["event"] == "done"
    finally:
        event_bus.unsubscribe(sub)


@pytest.mark.asyncio
async def test_publish_no_subscribers_drops_silently():
    await event_bus.publish(999, {"event": "x"})  # 不应抛
```

- [ ] **Step 2：失败跑**

```bash
cd backend && pytest tests/test_adaptation_event_bus.py -v
```
Expected: ImportError

- [ ] **Step 3：实现**

```python
# backend/app/services/adaptation_event_bus.py
"""单进程内的 version 级事件总线，用于 SSE 推送。

- 仅支持单 worker 部署（spec §10）。
- 订阅者按 version_id 分组；publish 时往该 version 的所有订阅者 queue 各 put 一份。
- 订阅者负责调用 unsubscribe 释放资源。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass
class _Subscriber:
    version_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, version_id: int) -> _Subscriber:
        sub = _Subscriber(version_id=version_id)
        self._subs.setdefault(version_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.version_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.version_id, None)

    async def publish(self, version_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(version_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                # 慢消费者：丢一个最老再塞，避免阻塞 publisher
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


event_bus = _EventBus()
```

- [ ] **Step 4：跑测试**

```bash
cd backend && pytest tests/test_adaptation_event_bus.py -v
```
Expected: 2 PASS

- [ ] **Step 5：提交**

```bash
git add backend/app/services/adaptation_event_bus.py backend/tests/test_adaptation_event_bus.py
git commit -m "feat(adaptation): version 级事件总线（SSE 推送基础）"
```

---

## Task 6：实体抽取 + LLM 切场 fallback 服务

**Files:**
- Create: `backend/app/services/adaptation_llm_service.py`
- Test: `backend/tests/test_adaptation_llm_service.py`

设计要点：把 LLM 调用收敛到一个 service，对外暴露 `extract_entities`、`split_by_llm`、`rewrite_scene` 三个 async 方法；内部走 `script_ai_service.get_provider()` 返回的 provider，便于 mock。

- [ ] **Step 1：写测试（mock provider）**

```python
# backend/tests/test_adaptation_llm_service.py
import json
import pytest
from unittest.mock import AsyncMock, patch

from app.services.adaptation_llm_service import AdaptationLLMService


@pytest.mark.asyncio
async def test_extract_entities_parses_json():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value=json.dumps({
        "entities": [{"type": "person", "text": "李铁柱", "count": 5, "sample_context": "..."}],
        "character_traits": [{"name": "李铁柱", "tags": ["重情义"]}],
    }))
    svc = AdaptationLLMService(provider=fake_provider)
    out = await svc.extract_entities("一段原文")
    assert out["entities"][0]["text"] == "李铁柱"
    assert out["character_traits"][0]["tags"] == ["重情义"]


@pytest.mark.asyncio
async def test_extract_entities_invalid_json_raises():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value="不是 JSON")
    svc = AdaptationLLMService(provider=fake_provider)
    with pytest.raises(ValueError):
        await svc.extract_entities("x")


@pytest.mark.asyncio
async def test_rewrite_scene_includes_locked_marker():
    fake_provider = AsyncMock()
    captured = {}

    async def fake_complete(prompt: str, **kw):
        captured["prompt"] = prompt
        return "改写后的场内容"

    fake_provider.complete = fake_complete
    svc = AdaptationLLMService(provider=fake_provider)

    out = await svc.rewrite_scene(
        scene_text="原文场",
        intensity=3,
        intent="搬到 1990 上海",
        era_target="1990 上海",
        mappings=[
            {"original_text": "李铁柱", "replacement_text": "陈豪", "locked": True, "entity_type": "person"},
            {"original_text": "长安", "replacement_text": "上海", "locked": False, "entity_type": "place"},
        ],
        prev_scene_summary="主角与师父告别",
        character_traits=[{"name": "李铁柱", "tags": ["重情义"]}],
        extra_prompt=None,
    )
    assert out == "改写后的场内容"
    assert "[LOCKED]" in captured["prompt"]
    assert "李铁柱" in captured["prompt"] and "陈豪" in captured["prompt"]
    assert "1990" in captured["prompt"]


@pytest.mark.asyncio
async def test_split_by_llm_parses_offset_array():
    fake_provider = AsyncMock()
    fake_provider.complete = AsyncMock(return_value=json.dumps([
        {"start": 0, "end": 10, "title": "场A"},
        {"start": 10, "end": 25, "title": "场B"},
    ]))
    svc = AdaptationLLMService(provider=fake_provider)
    bs = await svc.split_by_llm("一段没场标记的文本，凑长度到二十五个字符。")
    assert len(bs) == 2
    assert bs[0].title == "场A"
    assert bs[1].end == 25
```

- [ ] **Step 2：跑测试确认失败**

```bash
cd backend && pytest tests/test_adaptation_llm_service.py -v
```
Expected: ImportError

- [ ] **Step 3：实现**

```python
# backend/app/services/adaptation_llm_service.py
"""改编模块的 LLM 调用层，集中三个能力：抽实体 / LLM 切场 / 改写单场。

为便于测试，构造时可注入 provider；生产由 get_default_service() 用 script_ai_service 路由。
"""
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol

from app.core.config import settings
from app.services.adaptation_splitter import SceneBoundary

logger = logging.getLogger(__name__)


class _Provider(Protocol):
    async def complete(self, prompt: str, **kwargs) -> str: ...


_EXTRACT_PROMPT = """你是剧本改编实体抽取器。读下面的剧本原文，列出所有【人物 / 地点 / 关键道具 / 时代关键词】。

输出严格 JSON，禁止任何其他文字：
{{
  "entities": [
    {{"type": "person|place|prop|era_term", "text": "<原文出现形式>", "count": <出现次数>, "sample_context": "<≤30字示例>"}}
  ],
  "character_traits": [
    {{"name": "<人物名>", "tags": ["<≤8字标签>", "口头禅:<具体台词>"]}}
  ]
}}

要求：去重；同一实体不同写法合并；character_traits 仅产出主要人物（出场≥3次）。

原文：
{text}
"""

_SPLIT_PROMPT = """你是剧本场切分器。下面是缺少明显场标记的剧本原文。请按内在场景切分，输出严格 JSON，禁止任何其他文字：
[{{"start": <整数字符偏移>, "end": <整数字符偏移>, "title": "<≤30字场标题>"}}]

约束：start/end 为字符偏移，必须连续覆盖全文；标题为简短的"场N 地点/事件"。

原文（共 {length} 字符）：
{text}
"""

_REWRITE_INTENSITY_BODY = {
    1: "你只做精准的实体替换，处理同名消歧、称呼一致性、代词一致性。**严禁改动其他词。**",
    2: "你做实体替换，并对受替换影响的句子做最小润色（如骑马→开车需要调整动作描述）。**严禁增删对白行数；改写后的对白行数必须等于原文。**",
    3: "你按 era_target 重写场景中的物件、职业、动作、语言风格。必须保留：出场人物功能、冲突点、情感拐点、场内台词数量在原文 ±20% 以内、场次顺序与定位。",
}


@dataclass
class AdaptationLLMService:
    provider: _Provider
    extract_model: Optional[str] = None
    rewrite_model: Optional[str] = None

    async def extract_entities(self, text: str) -> Dict[str, Any]:
        raw = await self.provider.complete(
            _EXTRACT_PROMPT.format(text=text[: settings.ADAPTATION_MAX_CHARS]),
            model=self.extract_model,
        )
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.warning("extract_entities JSON 解析失败: %s; 原始: %s", e, raw[:200])
            raise ValueError(f"实体抽取返回非 JSON：{e}") from e
        data.setdefault("entities", [])
        data.setdefault("character_traits", [])
        return data

    async def split_by_llm(self, text: str) -> List[SceneBoundary]:
        raw = await self.provider.complete(
            _SPLIT_PROMPT.format(text=text, length=len(text)),
            model=self.extract_model,
        )
        try:
            arr = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 切场返回非 JSON：{e}") from e
        out: list[SceneBoundary] = []
        for i, item in enumerate(arr):
            out.append(SceneBoundary(
                index=i,
                start=int(item["start"]),
                end=int(item["end"]),
                title=str(item.get("title", f"场{i + 1}"))[:80],
            ))
        return out

    async def rewrite_scene(
        self,
        *,
        scene_text: str,
        intensity: int,
        intent: Optional[str],
        era_target: Optional[str],
        mappings: List[Dict[str, Any]],
        prev_scene_summary: Optional[str],
        character_traits: List[Dict[str, Any]],
        extra_prompt: Optional[str],
    ) -> str:
        body = _REWRITE_INTENSITY_BODY.get(intensity, _REWRITE_INTENSITY_BODY[2])

        mapping_lines = []
        for m in mappings:
            tag = "[LOCKED]" if m.get("locked") else ""
            repl = m.get("replacement_text") or "(待定)"
            mapping_lines.append(f"- {tag} [{m['entity_type']}] {m['original_text']} → {repl}")
        mapping_block = "\n".join(mapping_lines) if mapping_lines else "(无)"

        traits_block = "\n".join(
            f"- {t['name']}：{ '、'.join(t.get('tags', [])) }"
            for t in character_traits
        ) or "(无)"

        prompt = f"""你是剧本改编工程师。任务：在保剧情节奏不变的前提下，改写以下单场。

【强度规则】
{body}

【全局映射表（[LOCKED] 必须严格替换）】
{mapping_block}

【新时代/世界设定】
{era_target or "(未指定)"}

【改编意图】
{intent or "(未指定)"}

【人物性格标签】
{traits_block}

【上一场摘要】
{prev_scene_summary or "(本场为首场)"}

【额外要求】
{extra_prompt or "(无)"}

【原文场内容】
{scene_text}

请直接输出改写后的本场内容，不要任何解释或前后缀。"""

        return await self.provider.complete(prompt, model=self.rewrite_model)


def get_default_service() -> AdaptationLLMService:
    """使用现有 script_ai_service 的 provider。延迟 import 以避免循环依赖。"""
    from app.services.script_ai_service import get_provider  # type: ignore
    provider = get_provider()
    return AdaptationLLMService(
        provider=provider,
        extract_model=settings.ADAPTATION_EXTRACT_MODEL,
        rewrite_model=settings.ADAPTATION_REWRITE_MODEL,
    )
```

> **如果 `script_ai_service` 没有 `get_provider()` 函数**：先 grep 该文件找到合适的入口（可能叫 `_resolve_provider` 或 `script_ai_service.py` 里有一个全局 `service` 实例），然后把 `get_default_service()` 内部改成调用实际入口；保持外部接口不变。

- [ ] **Step 4：跑测试确认通过**

```bash
cd backend && pytest tests/test_adaptation_llm_service.py -v
```
Expected: 4 PASS

- [ ] **Step 5：提交**

```bash
git add backend/app/services/adaptation_llm_service.py backend/tests/test_adaptation_llm_service.py
git commit -m "feat(adaptation): LLM 服务层（抽实体/切场/改写）"
```

---

## Task 7：改编流水线编排（pipeline service）

**Files:**
- Create: `backend/app/services/adaptation_pipeline.py`
- Test: `backend/tests/test_adaptation_pipeline.py`

职责：把 PARSE/EXTRACT/SPLIT 串起来；REWRITE 子流程提供 `run_full(version)` / `rerun_scene(scene_result, extra_prompt)`；并发用 `asyncio.Semaphore`；每场 update DB 后 publish event。

- [ ] **Step 1：写测试（mock LLMService）**

```python
# backend/tests/test_adaptation_pipeline.py
import asyncio
import pytest
from sqlalchemy import select
from unittest.mock import AsyncMock

from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.services.adaptation_pipeline import AdaptationPipeline
from app.services.adaptation_splitter import SceneBoundary


@pytest.fixture
def fake_llm():
    svc = AsyncMock()
    svc.extract_entities = AsyncMock(return_value={
        "entities": [{"type": "person", "text": "李铁柱", "count": 3, "sample_context": "x"}],
        "character_traits": [{"name": "李铁柱", "tags": ["重情义"]}],
    })
    svc.split_by_llm = AsyncMock(return_value=[
        SceneBoundary(index=0, start=0, end=10, title="A"),
        SceneBoundary(index=1, start=10, end=20, title="B"),
    ])

    async def fake_rewrite(**kw):
        return "改:" + kw["scene_text"]
    svc.rewrite_scene = AsyncMock(side_effect=fake_rewrite)
    return svc


@pytest.mark.asyncio
async def test_extract_writes_mappings_and_traits(test_db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="A 李铁柱 B", intensity=2, status="ready")
    test_db_session.add(p); await test_db_session.commit()
    pipe = AdaptationPipeline(db=test_db_session, llm=fake_llm)
    await pipe.extract(p)
    rows = (await test_db_session.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
    )).scalars().all()
    assert any(r.original_text == "李铁柱" for r in rows)
    await test_db_session.refresh(p)
    assert p.metadata_["character_traits"][0]["name"] == "李铁柱"


@pytest.mark.asyncio
async def test_extract_preserves_locked(test_db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="李铁柱", intensity=1, status="ready")
    test_db_session.add(p); await test_db_session.flush()
    locked = AdaptationMappingEntry(project_id=p.id, entity_type="person",
                                     original_text="李铁柱", replacement_text="马克", locked=True)
    test_db_session.add(locked); await test_db_session.commit()

    pipe = AdaptationPipeline(db=test_db_session, llm=fake_llm)
    await pipe.extract(p)
    await test_db_session.refresh(locked)
    assert locked.replacement_text == "马克"
    assert locked.locked is True


@pytest.mark.asyncio
async def test_split_uses_regex_then_falls_back(test_db_session, test_user, fake_llm):
    p = AdaptationProject(user_id=test_user.id, title="t",
                          source_text="毫无场标记的散文一段二十字", intensity=2, status="ready")
    test_db_session.add(p); await test_db_session.commit()
    pipe = AdaptationPipeline(db=test_db_session, llm=fake_llm)
    await pipe.split(p)
    await test_db_session.refresh(p)
    assert p.metadata_["split_method"] == "llm"
    assert len(p.metadata_["scene_boundaries"]) == 2


@pytest.mark.asyncio
async def test_run_full_writes_scenes_and_marks_done(test_db_session, test_user, fake_llm):
    p = AdaptationProject(
        user_id=test_user.id, title="t", source_text="0123456789ABCDEFGHIJ",
        intensity=2, status="ready",
        metadata_={"scene_boundaries": [
            {"index": 0, "start": 0, "end": 10, "title": "A"},
            {"index": 1, "start": 10, "end": 20, "title": "B"},
        ], "scene_summaries": ["S0", "S1"], "character_traits": []},
    )
    test_db_session.add(p); await test_db_session.commit()
    pipe = AdaptationPipeline(db=test_db_session, llm=fake_llm, concurrency=2)
    version = await pipe.create_full_run(p)
    await pipe.execute_full_run(p, version)
    results = (await test_db_session.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == version.id)
        .order_by(AdaptationSceneResult.scene_index)
    )).scalars().all()
    assert len(results) == 2
    assert all(r.status == "done" for r in results)
    assert results[0].rewritten_scene_text.startswith("改:")
    await test_db_session.refresh(version)
    assert version.status == "done"


@pytest.mark.asyncio
async def test_run_full_partial_when_one_scene_fails(test_db_session, test_user, fake_llm):
    async def fake_rewrite(**kw):
        if kw["scene_text"].startswith("0"):
            raise RuntimeError("boom")
        return "OK"
    fake_llm.rewrite_scene = AsyncMock(side_effect=fake_rewrite)

    p = AdaptationProject(
        user_id=test_user.id, title="t", source_text="0123456789ABCDEFGHIJ",
        intensity=2, status="ready",
        metadata_={"scene_boundaries": [
            {"index": 0, "start": 0, "end": 10, "title": "A"},
            {"index": 1, "start": 10, "end": 20, "title": "B"},
        ], "scene_summaries": ["", ""], "character_traits": []},
    )
    test_db_session.add(p); await test_db_session.commit()
    pipe = AdaptationPipeline(db=test_db_session, llm=fake_llm, concurrency=2)
    v = await pipe.create_full_run(p)
    await pipe.execute_full_run(p, v)
    await test_db_session.refresh(v)
    assert v.status == "partial"
    assert v.stats["failed"] == 1 and v.stats["succeeded"] == 1
```

- [ ] **Step 2：跑测试确认失败**

```bash
cd backend && pytest tests/test_adaptation_pipeline.py -v
```
Expected: ImportError

- [ ] **Step 3：实现**

```python
# backend/app/services/adaptation_pipeline.py
"""改编流水线编排：parse → extract → split → run_full / rerun_scene。"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.adaptation_version import AdaptationVersion
from app.services.adaptation_event_bus import event_bus
from app.services.adaptation_llm_service import AdaptationLLMService
from app.services.adaptation_splitter import SceneBoundary, split_by_regex

logger = logging.getLogger(__name__)


def _line_count(s: str) -> int:
    return sum(1 for ln in s.splitlines() if ln.strip())


def _delta_pct(orig: str, new: str) -> float:
    o = _line_count(orig) or 1
    return (_line_count(new) - _line_count(orig)) / o


@dataclass
class AdaptationPipeline:
    db: AsyncSession
    llm: AdaptationLLMService
    concurrency: int = 0  # 0 = 用配置默认

    def _sem(self) -> asyncio.Semaphore:
        n = self.concurrency or settings.ADAPTATION_REWRITE_CONCURRENCY
        return asyncio.Semaphore(max(1, n))

    async def extract(self, project: AdaptationProject) -> None:
        """LLM 抽实体 + 性格标签；保留 locked 行不覆盖。"""
        try:
            data = await self.llm.extract_entities(project.source_text)
        except Exception as e:
            project.status = "extract_failed"
            await self.db.commit()
            raise

        existing_rows = (await self.db.execute(
            select(AdaptationMappingEntry).where(
                AdaptationMappingEntry.project_id == project.id
            )
        )).scalars().all()
        existing_origins = {r.original_text: r for r in existing_rows}

        order = max((r.order_index for r in existing_rows), default=-1) + 1
        for ent in data.get("entities", []):
            text = ent.get("text", "").strip()
            if not text or text in existing_origins:
                continue
            self.db.add(AdaptationMappingEntry(
                project_id=project.id,
                entity_type=ent.get("type", "other"),
                original_text=text,
                replacement_text=None,
                locked=False,
                order_index=order,
            ))
            order += 1

        meta = dict(project.metadata_ or {})
        meta["character_traits"] = data.get("character_traits", [])
        project.metadata_ = meta
        project.status = "ready"
        await self.db.commit()

    async def split(self, project: AdaptationProject) -> None:
        """切场：先正则；不命中走 LLM；最后兜底为单场。"""
        text = project.source_text
        boundaries = split_by_regex(text)
        method = "regex"
        if not boundaries:
            try:
                boundaries = await self.llm.split_by_llm(text)
                method = "llm"
            except Exception as e:
                logger.warning("LLM 切场失败，降级单场：%s", e)
                boundaries = [SceneBoundary(index=0, start=0, end=len(text), title="全文")]
                method = "fallback_single"

        meta = dict(project.metadata_ or {})
        meta["scene_boundaries"] = [
            {"index": b.index, "start": b.start, "end": b.end, "title": b.title}
            for b in boundaries
        ]
        meta["scene_summaries"] = meta.get("scene_summaries") or [""] * len(boundaries)
        if len(meta["scene_summaries"]) != len(boundaries):
            meta["scene_summaries"] = [""] * len(boundaries)
        meta["split_method"] = method
        project.metadata_ = meta
        project.status = "ready"
        await self.db.commit()

    async def create_full_run(
        self, project: AdaptationProject, *, extra_prompt: Optional[str] = None
    ) -> AdaptationVersion:
        max_no = (await self.db.execute(
            select(func.coalesce(func.max(AdaptationVersion.version_no), 0))
            .where(AdaptationVersion.project_id == project.id)
        )).scalar_one()

        mappings = (await self.db.execute(
            select(AdaptationMappingEntry)
            .where(AdaptationMappingEntry.project_id == project.id)
            .order_by(AdaptationMappingEntry.order_index)
        )).scalars().all()
        snapshot = [{
            "original_text": m.original_text,
            "replacement_text": m.replacement_text,
            "entity_type": m.entity_type,
            "locked": m.locked,
            "notes": m.notes,
        } for m in mappings]

        version = AdaptationVersion(
            project_id=project.id,
            version_no=int(max_no) + 1,
            triggered_by="full_run",
            status="running",
            mapping_snapshot=snapshot,
            prompt_overrides={"extra_prompt": extra_prompt} if extra_prompt else None,
        )
        self.db.add(version); await self.db.flush()

        boundaries = (project.metadata_ or {}).get("scene_boundaries", [])
        for b in boundaries:
            self.db.add(AdaptationSceneResult(
                version_id=version.id,
                scene_index=b["index"],
                scene_title=b["title"],
                original_scene_text=project.source_text[b["start"]:b["end"]],
                status="pending",
            ))
        project.status = "generating"
        await self.db.commit()
        return version

    async def execute_full_run(
        self, project: AdaptationProject, version: AdaptationVersion
    ) -> None:
        sem = self._sem()
        meta = project.metadata_ or {}
        summaries = meta.get("scene_summaries", [])
        traits = meta.get("character_traits", [])
        extra_prompt = (version.prompt_overrides or {}).get("extra_prompt")

        scenes = (await self.db.execute(
            select(AdaptationSceneResult)
            .where(AdaptationSceneResult.version_id == version.id)
            .order_by(AdaptationSceneResult.scene_index)
        )).scalars().all()

        async def _one(scene: AdaptationSceneResult):
            async with sem:
                await self._rewrite_one(
                    project=project, version=version, scene=scene,
                    prev_summary=summaries[scene.scene_index - 1] if scene.scene_index > 0 and scene.scene_index - 1 < len(summaries) else None,
                    traits=traits, mappings=version.mapping_snapshot or [],
                    extra_prompt=extra_prompt,
                )

        await asyncio.gather(*[_one(s) for s in scenes], return_exceptions=False)

        succeeded = sum(1 for s in scenes if s.status == "done")
        failed = sum(1 for s in scenes if s.status == "failed")
        if failed == 0:
            version.status = "done"
        elif succeeded == 0:
            version.status = "failed"
        else:
            version.status = "partial"
        version.completed_at = datetime.utcnow()
        version.stats = {
            "total_scenes": len(scenes),
            "succeeded": succeeded,
            "failed": failed,
            "total_tokens": sum((s.token_used or 0) for s in scenes),
        }
        project.status = "done"
        await self.db.commit()
        await event_bus.publish(version.id, {
            "event": "version_done", "version_id": version.id, "status": version.status,
        })

    async def _rewrite_one(
        self, *, project: AdaptationProject, version: AdaptationVersion,
        scene: AdaptationSceneResult, prev_summary: Optional[str],
        traits: List[Dict[str, Any]], mappings: List[Dict[str, Any]],
        extra_prompt: Optional[str],
    ) -> None:
        scene.status = "running"
        await self.db.commit()
        await event_bus.publish(version.id, {
            "event": "scene_running", "scene_index": scene.scene_index,
        })
        try:
            text = await asyncio.wait_for(
                self.llm.rewrite_scene(
                    scene_text=scene.original_scene_text,
                    intensity=project.intensity,
                    intent=project.intent,
                    era_target=project.era_target,
                    mappings=mappings,
                    prev_scene_summary=prev_summary,
                    character_traits=traits,
                    extra_prompt=extra_prompt,
                ),
                timeout=settings.ADAPTATION_PER_SCENE_TIMEOUT_SEC,
            )
            scene.rewritten_scene_text = text
            scene.status = "done"
            scene.line_count_delta_pct = _delta_pct(scene.original_scene_text, text)
        except Exception as e:
            scene.status = "failed"
            scene.error = str(e)[:500]
            logger.exception("场 %s 改写失败", scene.scene_index)
        await self.db.commit()
        await event_bus.publish(version.id, {
            "event": "scene_done",
            "scene_index": scene.scene_index,
            "status": scene.status,
            "rewritten": scene.rewritten_scene_text,
            "error": scene.error,
            "line_count_delta_pct": scene.line_count_delta_pct,
        })

    async def rerun_scene(
        self, project: AdaptationProject, version: AdaptationVersion,
        scene: AdaptationSceneResult, extra_prompt: Optional[str],
    ) -> None:
        if scene.status == "running":
            raise ValueError("该场正在跑，无法重跑")
        meta = project.metadata_ or {}
        summaries = meta.get("scene_summaries", [])
        traits = meta.get("character_traits", [])
        before = scene.rewritten_scene_text
        await self._rewrite_one(
            project=project, version=version, scene=scene,
            prev_summary=summaries[scene.scene_index - 1] if scene.scene_index > 0 and scene.scene_index - 1 < len(summaries) else None,
            traits=traits, mappings=version.mapping_snapshot or [],
            extra_prompt=extra_prompt,
        )
        edits = list(scene.manual_edits or [])
        edits.append({
            "type": "rerun", "at": datetime.utcnow().isoformat(),
            "prompt": extra_prompt, "before": before, "after": scene.rewritten_scene_text,
        })
        scene.manual_edits = edits
        await self.db.commit()
```

- [ ] **Step 4：跑测试确认通过**

```bash
cd backend && pytest tests/test_adaptation_pipeline.py -v
```
Expected: 5 PASS

- [ ] **Step 5：提交**

```bash
git add backend/app/services/adaptation_pipeline.py backend/tests/test_adaptation_pipeline.py
git commit -m "feat(adaptation): 流水线编排（extract/split/run_full/rerun）"
```

---

## Task 8：启动恢复 hook（清理 stale running）

**Files:**
- Create: `backend/app/services/adaptation_recovery.py`
- Modify: `backend/app/main.py`（在 lifespan 中调用）
- Test: `backend/tests/test_adaptation_recovery.py`

- [ ] **Step 1：写测试**

```python
# backend/tests/test_adaptation_recovery.py
import pytest
from datetime import datetime, timedelta
from sqlalchemy import select

from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.services.adaptation_recovery import cleanup_stale_runs


@pytest.mark.asyncio
async def test_cleanup_marks_old_running_as_failed(test_db_session, test_user):
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="generating")
    test_db_session.add(p); await test_db_session.flush()
    old = AdaptationVersion(
        project_id=p.id, version_no=1, status="running", triggered_by="full_run",
        created_at=datetime.utcnow() - timedelta(hours=2),
    )
    fresh = AdaptationVersion(
        project_id=p.id, version_no=2, status="running", triggered_by="full_run",
    )
    test_db_session.add_all([old, fresh]); await test_db_session.flush()
    test_db_session.add(AdaptationSceneResult(
        version_id=old.id, scene_index=0, original_scene_text="x", status="running"
    ))
    await test_db_session.commit()

    await cleanup_stale_runs(test_db_session, max_age_sec=3600)
    await test_db_session.refresh(old); await test_db_session.refresh(fresh)
    assert old.status == "failed" and old.error
    assert fresh.status == "running"
    s = (await test_db_session.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == old.id)
    )).scalar_one()
    assert s.status == "failed"
```

- [ ] **Step 2：跑测试确认失败**

```bash
cd backend && pytest tests/test_adaptation_recovery.py -v
```
Expected: ImportError

- [ ] **Step 3：实现**

```python
# backend/app/services/adaptation_recovery.py
"""服务启动时清理悬挂的 running 状态。"""
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.adaptation_scene_result import AdaptationSceneResult
from app.models.adaptation_version import AdaptationVersion


async def cleanup_stale_runs(db: AsyncSession, max_age_sec: int) -> int:
    cutoff = datetime.utcnow() - timedelta(seconds=max_age_sec)
    stale_versions = (await db.execute(
        select(AdaptationVersion).where(
            AdaptationVersion.status == "running",
            AdaptationVersion.created_at < cutoff,
        )
    )).scalars().all()
    for v in stale_versions:
        v.status = "failed"
        v.error = "服务重启时改编中断"
        await db.execute(
            update(AdaptationSceneResult)
            .where(
                AdaptationSceneResult.version_id == v.id,
                AdaptationSceneResult.status == "running",
            )
            .values(status="failed", error="服务重启时改编中断")
        )
    await db.commit()
    return len(stale_versions)
```

- [ ] **Step 4：在 `main.py` 的 lifespan 中调用**

打开 `backend/app/main.py`，找到：

```python
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库、启动定时任务"""
    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()
```

替换为：

```python
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库、启动定时任务、清理 stale 改编。"""
    await init_db()
    # 清理上次运行残留的改编 running 状态
    from app.core.database import async_session
    from app.services.adaptation_recovery import cleanup_stale_runs
    async with async_session() as session:
        await cleanup_stale_runs(session, max_age_sec=settings.ADAPTATION_STALE_RUN_CLEANUP_AGE_SEC)
    await start_scheduler()
    yield
    await stop_scheduler()
```

- [ ] **Step 5：跑测试**

```bash
cd backend && pytest tests/test_adaptation_recovery.py -v
```
Expected: 1 PASS

- [ ] **Step 6：提交**

```bash
git add backend/app/services/adaptation_recovery.py backend/app/main.py backend/tests/test_adaptation_recovery.py
git commit -m "feat(adaptation): 启动时清理 stale running 状态"
```

---

## Task 9：API Router 第一刀（项目 CRUD + extract + split + 映射）

**Files:**
- Create: `backend/app/routers/adaptation.py`
- Modify: `backend/app/routers/__init__.py`
- Modify: `backend/app/main.py`（include router）
- Test: `backend/tests/test_adaptation_router.py`

- [ ] **Step 1：写测试（覆盖创建、抽取、切场、映射、权限）**

```python
# backend/tests/test_adaptation_router.py
import pytest
from sqlalchemy import select

from app.models.adaptation_project import AdaptationProject


@pytest.mark.asyncio
async def test_create_project_with_text(client, auth_headers):
    r = await client.post("/api/v1/adaptation/projects",
                          json={"title": "改编1", "raw_text": "场1 长安城\n打斗\n场2 客栈\n对饮", "intensity": 2},
                          headers=auth_headers)
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["title"] == "改编1"
    assert data["status"] in ("ready", "parsing")


@pytest.mark.asyncio
async def test_list_only_my_projects(client, auth_headers, test_db_session, other_user):
    other = AdaptationProject(user_id=other_user.id, title="他人", source_text="x", intensity=1, status="ready")
    test_db_session.add(other); await test_db_session.commit()
    r = await client.get("/api/v1/adaptation/projects", headers=auth_headers)
    assert r.status_code == 200
    titles = [p["title"] for p in r.json()]
    assert "他人" not in titles


@pytest.mark.asyncio
async def test_extract_endpoint(monkeypatch, client, auth_headers):
    async def fake_extract(self, project):
        from app.models.adaptation_mapping_entry import AdaptationMappingEntry
        self.db.add(AdaptationMappingEntry(
            project_id=project.id, entity_type="person",
            original_text="李铁柱", locked=False, order_index=0,
        ))
        project.status = "ready"
        await self.db.commit()
    monkeypatch.setattr("app.services.adaptation_pipeline.AdaptationPipeline.extract", fake_extract)

    r = await client.post("/api/v1/adaptation/projects",
                          json={"title": "t", "raw_text": "李铁柱在长安城外", "intensity": 1},
                          headers=auth_headers)
    pid = r.json()["id"]
    r2 = await client.post(f"/api/v1/adaptation/projects/{pid}/extract", headers=auth_headers)
    assert r2.status_code == 200
    detail = await client.get(f"/api/v1/adaptation/projects/{pid}", headers=auth_headers)
    assert any(m["original_text"] == "李铁柱" for m in detail.json()["mappings"])


@pytest.mark.asyncio
async def test_mappings_bulk_put(client, auth_headers):
    r = await client.post("/api/v1/adaptation/projects",
                          json={"title": "t", "raw_text": "x", "intensity": 1}, headers=auth_headers)
    pid = r.json()["id"]
    r2 = await client.put(f"/api/v1/adaptation/projects/{pid}/mappings",
                          json={"entries": [
                              {"entity_type": "person", "original_text": "李铁柱",
                               "replacement_text": "马克", "locked": True, "order_index": 0},
                          ]}, headers=auth_headers)
    assert r2.status_code == 200
    detail = await client.get(f"/api/v1/adaptation/projects/{pid}", headers=auth_headers)
    assert detail.json()["mappings"][0]["replacement_text"] == "马克"
```

> conftest 需提供 `client`、`auth_headers`、`test_user`、`other_user`。若现有 conftest 无 `other_user` fixture，参考 `test_expansion_router.py` 创建一个并加入 conftest。

- [ ] **Step 2：跑测试确认失败**

```bash
cd backend && pytest tests/test_adaptation_router.py -v
```
Expected: 404 / NotFoundError

- [ ] **Step 3：实现 router 第一刀**

```python
# backend/app/routers/adaptation.py
"""剧本改编模块路由。"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.adaptation_project import AdaptationProject
from app.models.adaptation_mapping_entry import AdaptationMappingEntry
from app.models.adaptation_version import AdaptationVersion
from app.models.adaptation_scene_result import AdaptationSceneResult
from app.routers.auth import get_current_user
from app.schemas.adaptation import (
    AdaptationProjectCreate, AdaptationProjectUpdate, AdaptationProjectOut,
    AdaptationVersionOut, MappingsBulkPut, MappingEntryOut, SceneBoundary,
    MappingSuggestRequest,
)
from app.services.adaptation_pipeline import AdaptationPipeline
from app.services.adaptation_llm_service import get_default_service
from app.services.file_parser import FileParser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/adaptation", tags=["adaptation"])


def _word_count(text: str) -> int:
    import re
    return len(re.findall(r"[一-鿿]", text)) + len(re.findall(r"[a-zA-Z]+", text))


async def _get_owned_project(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdaptationProject:
    p = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.id == project_id)
    )).scalar_one_or_none()
    if not p or (p.user_id != current_user.id and not getattr(current_user, "is_superuser", False)):
        raise HTTPException(status_code=404, detail="改编项目不存在或无权访问")
    return p


def _project_to_out(p: AdaptationProject) -> dict:
    meta = p.metadata_ or {}
    return {
        "id": p.id, "title": p.title, "source_filename": p.source_filename,
        "intent": p.intent, "intensity": p.intensity, "era_target": p.era_target,
        "status": p.status, "created_at": p.created_at, "updated_at": p.updated_at,
        "word_count": _word_count(p.source_text),
        "scene_boundaries": meta.get("scene_boundaries", []),
        "versions": [
            {
                "id": v.id, "version_no": v.version_no, "triggered_by": v.triggered_by,
                "status": v.status, "stats": v.stats, "error": v.error,
                "created_at": v.created_at, "completed_at": v.completed_at,
            } for v in p.versions
        ],
        "mappings": [
            {
                "id": m.id, "entity_type": m.entity_type,
                "original_text": m.original_text, "replacement_text": m.replacement_text,
                "locked": m.locked, "notes": m.notes, "order_index": m.order_index,
            } for m in p.mappings
        ],
    }


@router.post("/projects", status_code=201, response_model=AdaptationProjectOut)
async def create_project(
    payload: AdaptationProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not payload.raw_text:
        raise HTTPException(400, "raw_text 不能为空（上传文件请用 /upload 端点）")
    if len(payload.raw_text) > settings.ADAPTATION_MAX_CHARS:
        raise HTTPException(400, f"原文超过 {settings.ADAPTATION_MAX_CHARS} 字上限")
    p = AdaptationProject(
        user_id=current_user.id, title=payload.title,
        source_text=payload.raw_text, intent=payload.intent,
        intensity=payload.intensity, era_target=payload.era_target,
        status="ready", metadata_={},
    )
    db.add(p); await db.commit(); await db.refresh(p)
    return _project_to_out(p)


@router.post("/projects/upload", status_code=201, response_model=AdaptationProjectOut)
async def create_project_upload(
    title: str = Form(...),
    intensity: int = Form(2),
    intent: str | None = Form(None),
    era_target: str | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = await file.read()
    parsed = FileParser.parse(content, file.filename)  # 沿用现有 API；若签名不同改成 parse_bytes
    if len(parsed.text) > settings.ADAPTATION_MAX_CHARS:
        raise HTTPException(400, f"原文超过 {settings.ADAPTATION_MAX_CHARS} 字上限")
    p = AdaptationProject(
        user_id=current_user.id, title=title, source_filename=file.filename,
        source_text=parsed.text, intent=intent, intensity=intensity,
        era_target=era_target, status="ready", metadata_={},
    )
    db.add(p); await db.commit(); await db.refresh(p)
    return _project_to_out(p)


@router.get("/projects", response_model=List[AdaptationProjectOut])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.user_id == current_user.id)
        .order_by(AdaptationProject.created_at.desc())
    )).scalars().all()
    return [_project_to_out(p) for p in rows]


@router.get("/projects/{project_id}", response_model=AdaptationProjectOut)
async def get_project(p: AdaptationProject = Depends(_get_owned_project)):
    return _project_to_out(p)


@router.patch("/projects/{project_id}", response_model=AdaptationProjectOut)
async def update_project(
    payload: AdaptationProjectUpdate,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    await db.commit(); await db.refresh(p)
    return _project_to_out(p)


@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(p); await db.commit()


@router.post("/projects/{project_id}/extract", response_model=AdaptationProjectOut)
async def extract(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    try:
        await pipe.extract(p)
    except Exception as e:
        raise HTTPException(502, f"实体抽取失败：{e}")
    await db.refresh(p)
    return _project_to_out(p)


@router.post("/projects/{project_id}/split", response_model=AdaptationProjectOut)
async def split(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    await pipe.split(p)
    await db.refresh(p)
    return _project_to_out(p)


@router.put("/projects/{project_id}/mappings", response_model=List[MappingEntryOut])
async def put_mappings(
    payload: MappingsBulkPut,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
    )
    for entry in payload.entries:
        db.add(AdaptationMappingEntry(project_id=p.id, **entry.model_dump()))
    await db.commit()
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()
    return [
        {"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
         "replacement_text": m.replacement_text, "locked": m.locked,
         "notes": m.notes, "order_index": m.order_index}
        for m in rows
    ]


@router.post("/projects/{project_id}/mappings/suggest", response_model=List[MappingEntryOut])
async def suggest_mappings(
    payload: MappingSuggestRequest,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    """让 LLM 给空 replacement 生成建议（基于 intent + era_target）。仅 MVP 简实现，可后续优化。"""
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()

    targets = [r for r in rows if (not payload.only_empty) or not r.replacement_text]
    if not targets:
        return [{"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
                 "replacement_text": m.replacement_text, "locked": m.locked,
                 "notes": m.notes, "order_index": m.order_index} for m in rows]

    import json
    svc = get_default_service()
    prompt = (
        f"你是剧本改编助手。新时代/世界设定：{p.era_target or '未指定'}；"
        f"改编意图：{p.intent or '未指定'}。\n"
        "为下列原词建议一个合适的新名称，输出严格 JSON：[{\"original\": \"...\", \"replacement\": \"...\"}]\n"
        + json.dumps([{"original": t.original_text, "type": t.entity_type} for t in targets], ensure_ascii=False)
    )
    raw = await svc.provider.complete(prompt, model=svc.extract_model)
    try:
        sugg = {item["original"]: item["replacement"] for item in json.loads(raw)}
    except Exception:
        sugg = {}
    for t in targets:
        if t.original_text in sugg and not t.locked:
            t.replacement_text = sugg[t.original_text]
    await db.commit()
    rows = (await db.execute(
        select(AdaptationMappingEntry).where(AdaptationMappingEntry.project_id == p.id)
        .order_by(AdaptationMappingEntry.order_index)
    )).scalars().all()
    return [{"id": m.id, "entity_type": m.entity_type, "original_text": m.original_text,
             "replacement_text": m.replacement_text, "locked": m.locked,
             "notes": m.notes, "order_index": m.order_index} for m in rows]
```

- [ ] **Step 4：注册到 routers/__init__.py 与 main.py**

`backend/app/routers/__init__.py` 在末尾追加：

```python
from app.routers.adaptation import router as adaptation_router
```

并在 `__all__` 追加 `"adaptation_router"`。

`backend/app/main.py` 找到 router 注册区（搜索 `app.include_router` 或 `from app.routers import` 列表），按现有风格新增：

```python
from app.routers import (
    ...
    adaptation_router,
)
...
app.include_router(adaptation_router)
```

> 若现有 main.py 是用 `app.include_router(expansion_router)` 这种写法，按同款风格加一行；若是循环注册，也按同款。

- [ ] **Step 5：跑测试确认通过**

```bash
cd backend && pytest tests/test_adaptation_router.py -v
```
Expected: 4 PASS

> 若 `FileParser.parse(content, filename)` 签名实际不同（旧签名可能是 `parse_bytes(content, filename)` 或 `from_upload(file)`），用 grep 找到实际函数名后替换。

- [ ] **Step 6：提交**

```bash
git add backend/app/routers/adaptation.py backend/app/routers/__init__.py backend/app/main.py backend/tests/test_adaptation_router.py
git commit -m "feat(adaptation): API 路由第一刀（CRUD + extract + split + 映射）"
```

---

## Task 10：API Router 第二刀（runs / SSE / rerun / 手改 / 导出）

**Files:**
- Modify: `backend/app/routers/adaptation.py`
- Test: 追加到 `backend/tests/test_adaptation_router.py`

- [ ] **Step 1：先在路由文件追加 endpoint**

在 `app/routers/adaptation.py` 末尾追加：

```python
import asyncio
import json
from datetime import datetime
from io import BytesIO

from fastapi.responses import StreamingResponse
from app.services.adaptation_event_bus import event_bus
from app.schemas.adaptation import (
    RunCreate, SceneRerunRequest, SceneManualPatch,
    VersionDetailOut, SceneResultOut, AdaptationVersionOut,
)


def _scene_to_out(s) -> dict:
    return {
        "id": s.id, "scene_index": s.scene_index, "scene_title": s.scene_title,
        "status": s.status, "error": s.error, "token_used": s.token_used,
        "line_count_delta_pct": s.line_count_delta_pct,
        "original_scene_text": s.original_scene_text,
        "rewritten_scene_text": s.rewritten_scene_text,
        "manual_edits": s.manual_edits or [],
        "updated_at": s.updated_at,
    }


def _version_to_out(v) -> dict:
    return {
        "id": v.id, "version_no": v.version_no, "triggered_by": v.triggered_by,
        "status": v.status, "stats": v.stats, "error": v.error,
        "created_at": v.created_at, "completed_at": v.completed_at,
    }


async def _get_owned_version(
    version_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AdaptationVersion:
    v = (await db.execute(
        select(AdaptationVersion).where(AdaptationVersion.id == version_id)
    )).scalar_one_or_none()
    if not v:
        raise HTTPException(404, "version 不存在")
    p = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.id == v.project_id)
    )).scalar_one()
    if p.user_id != current_user.id and not getattr(current_user, "is_superuser", False):
        raise HTTPException(404, "无权访问")
    return v


@router.post("/projects/{project_id}/runs", response_model=AdaptationVersionOut)
async def create_run(
    payload: RunCreate,
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    if not (p.metadata_ or {}).get("scene_boundaries"):
        raise HTTPException(400, "尚未切场，请先调用 /split")
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    version = await pipe.create_full_run(p, extra_prompt=payload.extra_prompt)
    # 后台异步执行，不阻塞响应
    asyncio.create_task(_background_run(p.id, version.id))
    return _version_to_out(version)


async def _background_run(project_id: int, version_id: int) -> None:
    """后台 task：用一个新的 db session 执行实际改写。"""
    from app.core.database import async_session
    async with async_session() as session:
        p = (await session.execute(
            select(AdaptationProject).where(AdaptationProject.id == project_id)
        )).scalar_one_or_none()
        v = (await session.execute(
            select(AdaptationVersion).where(AdaptationVersion.id == version_id)
        )).scalar_one_or_none()
        if not p or not v:
            return
        pipe = AdaptationPipeline(db=session, llm=get_default_service())
        try:
            await pipe.execute_full_run(p, v)
        except Exception as e:
            logger.exception("背景跑改编失败")
            v.status = "failed"
            v.error = str(e)[:500]
            await session.commit()
            await event_bus.publish(version_id, {"event": "version_failed", "error": str(e)[:200]})


@router.get("/projects/{project_id}/runs", response_model=List[AdaptationVersionOut])
async def list_runs(
    p: AdaptationProject = Depends(_get_owned_project),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(AdaptationVersion).where(AdaptationVersion.project_id == p.id)
        .order_by(AdaptationVersion.version_no.desc())
    )).scalars().all()
    return [_version_to_out(v) for v in rows]


@router.get("/runs/{version_id}", response_model=VersionDetailOut)
async def get_version(
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    scenes = (await db.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == v.id)
        .order_by(AdaptationSceneResult.scene_index)
    )).scalars().all()
    return {**_version_to_out(v), "scene_results": [_scene_to_out(s) for s in scenes]}


@router.get("/runs/{version_id}/stream")
async def stream_run(v: AdaptationVersion = Depends(_get_owned_version)):
    sub = event_bus.subscribe(v.id)

    async def gen():
        try:
            # 立即推一条心跳，避免代理超时
            yield "data: " + json.dumps({"event": "subscribed", "version_id": v.id}) + "\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(sub.queue.get(), timeout=15.0)
                    yield "data: " + json.dumps(payload, default=str) + "\n\n"
                    if payload.get("event") in ("version_done", "version_failed"):
                        return
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # SSE 注释行做心跳
        finally:
            event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/runs/{version_id}/scenes/{scene_index}/rerun", response_model=SceneResultOut)
async def rerun_scene(
    scene_index: int,
    payload: SceneRerunRequest,
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    scene = (await db.execute(
        select(AdaptationSceneResult).where(
            AdaptationSceneResult.version_id == v.id,
            AdaptationSceneResult.scene_index == scene_index,
        )
    )).scalar_one_or_none()
    if not scene:
        raise HTTPException(404, "scene 不存在")
    if scene.status == "running":
        raise HTTPException(409, "该场正在跑，无法重跑")
    p = (await db.execute(
        select(AdaptationProject).where(AdaptationProject.id == v.project_id)
    )).scalar_one()
    pipe = AdaptationPipeline(db=db, llm=get_default_service())
    try:
        await pipe.rerun_scene(p, v, scene, payload.extra_prompt)
    except ValueError as e:
        raise HTTPException(409, str(e))
    return _scene_to_out(scene)


@router.patch("/runs/{version_id}/scenes/{scene_index}", response_model=SceneResultOut)
async def patch_scene(
    scene_index: int,
    payload: SceneManualPatch,
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    scene = (await db.execute(
        select(AdaptationSceneResult).where(
            AdaptationSceneResult.version_id == v.id,
            AdaptationSceneResult.scene_index == scene_index,
        )
    )).scalar_one_or_none()
    if not scene:
        raise HTTPException(404, "scene 不存在")
    edits = list(scene.manual_edits or [])
    edits.append({
        "type": "manual", "at": datetime.utcnow().isoformat(),
        "before": scene.rewritten_scene_text, "after": payload.rewritten_scene_text,
    })
    scene.manual_edits = edits
    scene.rewritten_scene_text = payload.rewritten_scene_text
    scene.status = "manual_edited"
    await db.commit()
    return _scene_to_out(scene)


@router.get("/runs/{version_id}/export")
async def export_run(
    format: str = "txt",
    v: AdaptationVersion = Depends(_get_owned_version),
    db: AsyncSession = Depends(get_db),
):
    if format not in ("txt", "docx"):
        raise HTTPException(400, "format 仅支持 txt/docx")
    scenes = (await db.execute(
        select(AdaptationSceneResult).where(AdaptationSceneResult.version_id == v.id)
        .order_by(AdaptationSceneResult.scene_index)
    )).scalars().all()
    parts = [s.rewritten_scene_text or s.original_scene_text for s in scenes]
    text = "\n\n".join(parts)

    if format == "txt":
        return StreamingResponse(
            BytesIO(text.encode("utf-8")), media_type="text/plain",
            headers={"Content-Disposition": f"attachment; filename=adaptation_v{v.version_no}.txt"},
        )

    # docx
    from docx import Document  # python-docx 已在 requirements
    doc = Document()
    for s in scenes:
        if s.scene_title:
            doc.add_heading(s.scene_title, level=2)
        doc.add_paragraph(s.rewritten_scene_text or s.original_scene_text)
    buf = BytesIO()
    doc.save(buf); buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=adaptation_v{v.version_no}.docx"},
    )
```

- [ ] **Step 2：追加测试到 `test_adaptation_router.py`**

```python
@pytest.mark.asyncio
async def test_run_full_creates_version_and_marks_done(monkeypatch, client, auth_headers):
    # 让 LLM 抽实体直接回 mock，让切场走正则，让 rewrite 直返回原文上加前缀
    async def fake_extract(self, project):
        from app.models.adaptation_mapping_entry import AdaptationMappingEntry
        self.db.add(AdaptationMappingEntry(project_id=project.id, entity_type="person",
                                            original_text="李铁柱", order_index=0))
        meta = dict(project.metadata_ or {})
        meta["character_traits"] = []
        project.metadata_ = meta
        project.status = "ready"
        await self.db.commit()

    async def fake_rewrite(self, **kw):
        return "改:" + kw["scene_text"]

    monkeypatch.setattr("app.services.adaptation_pipeline.AdaptationPipeline.extract", fake_extract)
    monkeypatch.setattr("app.services.adaptation_llm_service.AdaptationLLMService.rewrite_scene", fake_rewrite)

    text = "场1 长安城外\n李铁柱挥剑\n场2 客栈\n二人对饮"
    r = await client.post("/api/v1/adaptation/projects",
                          json={"title": "t", "raw_text": text, "intensity": 1}, headers=auth_headers)
    pid = r.json()["id"]
    await client.post(f"/api/v1/adaptation/projects/{pid}/extract", headers=auth_headers)
    r2 = await client.post(f"/api/v1/adaptation/projects/{pid}/split", headers=auth_headers)
    assert len(r2.json()["scene_boundaries"]) == 2
    r3 = await client.post(f"/api/v1/adaptation/projects/{pid}/runs",
                           json={"extra_prompt": None}, headers=auth_headers)
    assert r3.status_code == 200
    vid = r3.json()["id"]

    # 后台 task；轮询直到 done
    import asyncio
    for _ in range(30):
        detail = await client.get(f"/api/v1/adaptation/runs/{vid}", headers=auth_headers)
        if detail.json()["status"] in ("done", "partial", "failed"):
            break
        await asyncio.sleep(0.05)
    assert detail.json()["status"] == "done"
    assert all(s["rewritten_scene_text"].startswith("改:") for s in detail.json()["scene_results"])


@pytest.mark.asyncio
async def test_manual_patch_marks_manual_edited(monkeypatch, client, auth_headers, test_db_session, test_user):
    from app.models.adaptation_project import AdaptationProject
    from app.models.adaptation_version import AdaptationVersion
    from app.models.adaptation_scene_result import AdaptationSceneResult
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="done")
    test_db_session.add(p); await test_db_session.flush()
    v = AdaptationVersion(project_id=p.id, version_no=1, status="done", triggered_by="full_run")
    test_db_session.add(v); await test_db_session.flush()
    s = AdaptationSceneResult(version_id=v.id, scene_index=0,
                               original_scene_text="原", rewritten_scene_text="AI 改", status="done")
    test_db_session.add(s); await test_db_session.commit()

    r = await client.patch(f"/api/v1/adaptation/runs/{v.id}/scenes/0",
                           json={"rewritten_scene_text": "我改"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["rewritten_scene_text"] == "我改"
    assert body["status"] == "manual_edited"
    assert body["manual_edits"][-1]["after"] == "我改"


@pytest.mark.asyncio
async def test_export_txt(client, auth_headers, test_db_session, test_user):
    from app.models.adaptation_project import AdaptationProject
    from app.models.adaptation_version import AdaptationVersion
    from app.models.adaptation_scene_result import AdaptationSceneResult
    p = AdaptationProject(user_id=test_user.id, title="t", source_text="x", intensity=1, status="done")
    test_db_session.add(p); await test_db_session.flush()
    v = AdaptationVersion(project_id=p.id, version_no=1, status="done", triggered_by="full_run")
    test_db_session.add(v); await test_db_session.flush()
    test_db_session.add_all([
        AdaptationSceneResult(version_id=v.id, scene_index=0, original_scene_text="o0",
                               rewritten_scene_text="r0", status="done"),
        AdaptationSceneResult(version_id=v.id, scene_index=1, original_scene_text="o1",
                               rewritten_scene_text="r1", status="done"),
    ])
    await test_db_session.commit()

    r = await client.get(f"/api/v1/adaptation/runs/{v.id}/export?format=txt", headers=auth_headers)
    assert r.status_code == 200
    assert r.text == "r0\n\nr1"
```

- [ ] **Step 3：跑测试**

```bash
cd backend && pytest tests/test_adaptation_router.py -v
```
Expected: 7 PASS（含 Task 9 的 4 条 + 本步 3 条）

- [ ] **Step 4：提交**

```bash
git add backend/app/routers/adaptation.py backend/tests/test_adaptation_router.py
git commit -m "feat(adaptation): API 第二刀（runs/SSE/rerun/手改/导出）"
```

---

## Task 11：前端 API 客户端

**Files:**
- Create: `frontend/src/api/adaptation.ts`

- [ ] **Step 1：参考 `frontend/src/api/expansion.ts`（若存在）的风格写一个 axios 封装**

先确认 axios 客户端来源：

```bash
grep -rn "axios.create\|export const api\|http\.get" frontend/src/api/ | head -5
```

- [ ] **Step 2：实现**

```typescript
// frontend/src/api/adaptation.ts
import http from './http' // 若现有项目导出叫别的，按实际改

export type EntityType = 'person' | 'place' | 'prop' | 'era_term' | 'other'

export interface MappingEntry {
  id?: number
  entity_type: EntityType
  original_text: string
  replacement_text?: string | null
  locked: boolean
  notes?: string | null
  order_index: number
}

export interface SceneBoundary {
  index: number
  start: number
  end: number
  title: string
}

export interface AdaptationVersion {
  id: number
  version_no: number
  triggered_by: string
  status: 'running' | 'done' | 'partial' | 'failed'
  stats?: any
  error?: string | null
  created_at: string
  completed_at?: string | null
}

export interface SceneResult {
  id: number
  scene_index: number
  scene_title?: string
  status: 'pending' | 'running' | 'done' | 'failed' | 'manual_edited'
  error?: string | null
  token_used?: number
  line_count_delta_pct?: number | null
  original_scene_text: string
  rewritten_scene_text?: string | null
  manual_edits?: any[]
  updated_at: string
}

export interface AdaptationProject {
  id: number
  title: string
  source_filename?: string
  intent?: string | null
  intensity: number
  era_target?: string | null
  status: string
  created_at: string
  updated_at: string
  word_count: number
  scene_boundaries: SceneBoundary[]
  versions: AdaptationVersion[]
  mappings: MappingEntry[]
}

const base = '/api/v1/adaptation'

export const adaptationApi = {
  list: () => http.get<AdaptationProject[]>(`${base}/projects`),
  get: (id: number) => http.get<AdaptationProject>(`${base}/projects/${id}`),
  createWithText: (payload: {title: string; raw_text: string; intent?: string; intensity: number; era_target?: string}) =>
    http.post<AdaptationProject>(`${base}/projects`, payload),
  createWithUpload: (form: FormData) =>
    http.post<AdaptationProject>(`${base}/projects/upload`, form, {
      headers: {'Content-Type': 'multipart/form-data'},
    }),
  update: (id: number, payload: Partial<{title: string; intent: string; intensity: number; era_target: string}>) =>
    http.patch<AdaptationProject>(`${base}/projects/${id}`, payload),
  remove: (id: number) => http.delete(`${base}/projects/${id}`),
  extract: (id: number) => http.post<AdaptationProject>(`${base}/projects/${id}/extract`),
  split: (id: number) => http.post<AdaptationProject>(`${base}/projects/${id}/split`),
  putMappings: (id: number, entries: MappingEntry[]) =>
    http.put<MappingEntry[]>(`${base}/projects/${id}/mappings`, {entries}),
  suggestMappings: (id: number) =>
    http.post<MappingEntry[]>(`${base}/projects/${id}/mappings/suggest`, {only_empty: true}),
  createRun: (id: number, extra_prompt?: string) =>
    http.post<AdaptationVersion>(`${base}/projects/${id}/runs`, {extra_prompt}),
  listRuns: (id: number) => http.get<AdaptationVersion[]>(`${base}/projects/${id}/runs`),
  getRun: (vid: number) =>
    http.get<AdaptationVersion & {scene_results: SceneResult[]}>(`${base}/runs/${vid}`),
  rerunScene: (vid: number, idx: number, extra_prompt?: string) =>
    http.post<SceneResult>(`${base}/runs/${vid}/scenes/${idx}/rerun`, {extra_prompt}),
  patchScene: (vid: number, idx: number, rewritten: string) =>
    http.patch<SceneResult>(`${base}/runs/${vid}/scenes/${idx}`, {rewritten_scene_text: rewritten}),
  exportUrl: (vid: number, format: 'txt' | 'docx') =>
    `${base}/runs/${vid}/export?format=${format}`,
  streamUrl: (vid: number) => `${base}/runs/${vid}/stream`,
}
```

> 若 `http` 入口实际叫 `request` / `apiClient` 等，按 grep 结果替换。

- [ ] **Step 3：build 检查**

```bash
cd frontend && npm run build 2>&1 | tail -20
```
Expected: 成功（无新错误）

- [ ] **Step 4：提交**

```bash
git add frontend/src/api/adaptation.ts
git commit -m "feat(adaptation): 前端 API 客户端"
```

---

## Task 12：列表页 `AdaptationListView.vue`

**Files:**
- Create: `frontend/src/views/AdaptationListView.vue`

- [ ] **Step 1：实现**

```vue
<!-- frontend/src/views/AdaptationListView.vue -->
<template>
  <div class="adaptation-list">
    <div class="header">
      <h2>我的剧本改编</h2>
      <el-button type="primary" @click="$router.push('/adaptation/create')">
        新建改编
      </el-button>
    </div>

    <el-empty v-if="!loading && projects.length === 0" description="还没有改编项目" />

    <div class="cards">
      <el-card
        v-for="p in projects"
        :key="p.id"
        class="card"
        shadow="hover"
        @click="$router.push(`/adaptation/workbench/${p.id}`)"
      >
        <div class="card-title">{{ p.title }}</div>
        <div class="card-meta">
          <el-tag size="small">强度 {{ p.intensity }}</el-tag>
          <el-tag size="small" :type="statusTag(p.status)">{{ p.status }}</el-tag>
          <span class="version-no">v{{ latestVersion(p) }}</span>
        </div>
        <div class="card-foot">
          <span>{{ p.word_count }} 字</span>
          <span>{{ formatTime(p.created_at) }}</span>
          <el-button type="danger" link size="small" @click.stop="confirmDelete(p)">删除</el-button>
        </div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adaptationApi, type AdaptationProject } from '@/api/adaptation'

const projects = ref<AdaptationProject[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const r = await adaptationApi.list()
    projects.value = r.data
  } finally {
    loading.value = false
  }
}

function latestVersion(p: AdaptationProject) {
  return p.versions.length ? Math.max(...p.versions.map(v => v.version_no)) : '-'
}

function statusTag(s: string): 'success' | 'warning' | 'danger' | 'info' | '' {
  if (s === 'done') return 'success'
  if (s === 'generating' || s === 'extracting') return 'warning'
  if (s.endsWith('_failed') || s === 'failed') return 'danger'
  return ''
}

function formatTime(s: string) {
  return new Date(s).toLocaleString()
}

async function confirmDelete(p: AdaptationProject) {
  await ElMessageBox.confirm(`删除「${p.title}」？此操作不可撤销。`, '确认', {type: 'warning'})
  await adaptationApi.remove(p.id)
  ElMessage.success('已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.adaptation-list { padding: 24px; max-width: 1200px; margin: 0 auto; }
.header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.card { cursor: pointer; }
.card-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.card-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.version-no { color: #909399; font-size: 12px; }
.card-foot { display: flex; justify-content: space-between; color: #909399; font-size: 12px; align-items: center; }
</style>
```

- [ ] **Step 2：build 检查**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3：提交**

```bash
git add frontend/src/views/AdaptationListView.vue
git commit -m "feat(adaptation): 列表页"
```

---

## Task 13：创建页 `AdaptationCreateView.vue`

**Files:**
- Create: `frontend/src/views/AdaptationCreateView.vue`

- [ ] **Step 1：实现（4 区块上下堆叠）**

```vue
<!-- frontend/src/views/AdaptationCreateView.vue -->
<template>
  <div class="adaptation-create">
    <h2>新建剧本改编</h2>

    <!-- 区块 1：标题 + 导入/粘贴 -->
    <el-card class="block">
      <template #header><strong>① 导入剧本</strong></template>
      <el-form label-width="100px">
        <el-form-item label="标题">
          <el-input v-model="title" placeholder="给这次改编起个名字" />
        </el-form-item>
        <el-form-item label="来源">
          <el-radio-group v-model="sourceMode">
            <el-radio value="paste">粘贴文本</el-radio>
            <el-radio value="upload">上传文件</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="sourceMode === 'paste'" label="原文">
          <el-input v-model="rawText" type="textarea" :rows="10" />
        </el-form-item>
        <el-form-item v-else label="文件">
          <el-upload :auto-upload="false" :on-change="onFileChange" :limit="1" :file-list="fileList">
            <el-button>选择 .txt / .docx</el-button>
          </el-upload>
        </el-form-item>
        <el-button type="primary" :loading="creating" @click="onCreate">创建项目</el-button>
      </el-form>
    </el-card>

    <!-- 区块 2：抽实体 + 映射表 -->
    <el-card v-if="project" class="block">
      <template #header>
        <div class="block-head">
          <strong>② 实体映射</strong>
          <div>
            <el-button :loading="extracting" @click="onExtract">AI 抽实体</el-button>
            <el-button :loading="suggesting" @click="onSuggest">AI 建议替换</el-button>
          </div>
        </div>
      </template>
      <el-table :data="mappings" size="small" empty-text="尚未抽取，点击「AI 抽实体」">
        <el-table-column prop="entity_type" label="类型" width="100">
          <template #default="{row}">
            <el-select v-model="row.entity_type" size="small">
              <el-option v-for="t in entityTypes" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="原文" width="180">
          <template #default="{row}"><el-input v-model="row.original_text" size="small" /></template>
        </el-table-column>
        <el-table-column label="替换为" width="180">
          <template #default="{row}">
            <el-input v-model="row.replacement_text" size="small" placeholder="留空=待 AI 建议" />
          </template>
        </el-table-column>
        <el-table-column label="锁定" width="60">
          <template #default="{row}"><el-checkbox v-model="row.locked" /></template>
        </el-table-column>
        <el-table-column label="备注">
          <template #default="{row}"><el-input v-model="row.notes" size="small" /></template>
        </el-table-column>
        <el-table-column label="" width="60">
          <template #default="{$index}">
            <el-button link type="danger" @click="mappings.splice($index, 1)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="block-actions">
        <el-button size="small" @click="addMapping">添加一行</el-button>
        <el-button size="small" type="primary" @click="saveMappings">保存映射</el-button>
      </div>
    </el-card>

    <!-- 区块 3：强度 + 意图 + 设定 -->
    <el-card v-if="project" class="block">
      <template #header><strong>③ 改编强度与设定</strong></template>
      <el-form label-width="100px">
        <el-form-item label="强度">
          <el-slider v-model="intensity" :min="1" :max="3" :marks="{1:'替换', 2:'润色', 3:'重铸'}" />
        </el-form-item>
        <el-form-item label="改编意图">
          <el-input v-model="intent" type="textarea" :rows="2" placeholder="如：改成 1990 年代上海背景" />
        </el-form-item>
        <el-form-item label="新设定">
          <el-input v-model="eraTarget" type="textarea" :rows="3" placeholder="新时代/世界设定的细节描述" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 区块 4：切场预览 -->
    <el-card v-if="project" class="block">
      <template #header>
        <div class="block-head">
          <strong>④ 场切分预览</strong>
          <el-button :loading="splitting" @click="onSplit">{{ project.scene_boundaries.length ? '重新切场' : '开始切场' }}</el-button>
        </div>
      </template>
      <el-collapse v-if="project.scene_boundaries.length">
        <el-collapse-item v-for="b in project.scene_boundaries" :key="b.index" :title="`场 ${b.index + 1}：${b.title}`">
          <div class="scene-preview">{{ project.scene_boundaries.length ? snippet(b) : '' }}</div>
        </el-collapse-item>
      </el-collapse>
      <el-empty v-else description="尚未切场" />
    </el-card>

    <div v-if="project && project.scene_boundaries.length" class="footer-actions">
      <el-button size="large" type="primary" @click="goWorkbench">进入工作台开始改编 →</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adaptationApi, type AdaptationProject, type EntityType, type MappingEntry } from '@/api/adaptation'

const router = useRouter()

const sourceMode = ref<'paste' | 'upload'>('paste')
const title = ref('')
const rawText = ref('')
const fileList = ref<any[]>([])
const intensity = ref(2)
const intent = ref('')
const eraTarget = ref('')

const project = ref<AdaptationProject | null>(null)
const mappings = ref<MappingEntry[]>([])
const entityTypes: EntityType[] = ['person', 'place', 'prop', 'era_term', 'other']

const creating = ref(false)
const extracting = ref(false)
const suggesting = ref(false)
const splitting = ref(false)

function onFileChange(file: any) { fileList.value = [file] }

async function onCreate() {
  if (!title.value.trim()) { ElMessage.warning('请填标题'); return }
  creating.value = true
  try {
    let r
    if (sourceMode.value === 'paste') {
      r = await adaptationApi.createWithText({
        title: title.value, raw_text: rawText.value,
        intent: intent.value || undefined, intensity: intensity.value,
        era_target: eraTarget.value || undefined,
      })
    } else {
      const fm = new FormData()
      fm.append('title', title.value)
      fm.append('intensity', String(intensity.value))
      if (intent.value) fm.append('intent', intent.value)
      if (eraTarget.value) fm.append('era_target', eraTarget.value)
      fm.append('file', fileList.value[0]?.raw)
      r = await adaptationApi.createWithUpload(fm)
    }
    project.value = r.data
    mappings.value = r.data.mappings || []
    ElMessage.success('项目已创建，可继续抽实体/切场')
  } finally { creating.value = false }
}

async function onExtract() {
  if (!project.value) return
  extracting.value = true
  try {
    const r = await adaptationApi.extract(project.value.id)
    project.value = r.data; mappings.value = r.data.mappings
    ElMessage.success(`抽出 ${r.data.mappings.length} 条`)
  } finally { extracting.value = false }
}

async function onSuggest() {
  if (!project.value) return
  suggesting.value = true
  try {
    await saveMappings()
    const r = await adaptationApi.suggestMappings(project.value.id)
    mappings.value = r.data
  } finally { suggesting.value = false }
}

function addMapping() {
  mappings.value.push({entity_type: 'person', original_text: '', replacement_text: '', locked: false, notes: '', order_index: mappings.value.length})
}

async function saveMappings() {
  if (!project.value) return
  for (let i = 0; i < mappings.value.length; i++) mappings.value[i].order_index = i
  await adaptationApi.putMappings(project.value.id, mappings.value)
  // 顺带保存 intent/intensity/era_target
  await adaptationApi.update(project.value.id, {
    intent: intent.value, intensity: intensity.value, era_target: eraTarget.value,
  })
  ElMessage.success('已保存')
}

async function onSplit() {
  if (!project.value) return
  await saveMappings()
  splitting.value = true
  try {
    const r = await adaptationApi.split(project.value.id)
    project.value = r.data
    ElMessage.success(`切出 ${r.data.scene_boundaries.length} 场`)
  } finally { splitting.value = false }
}

function snippet(b: any) {
  if (!project.value) return ''
  // 此处不持有原文，预览仅显示标题；详细预览留给工作台
  return `字符 ${b.start} - ${b.end}（${b.end - b.start} 字）`
}

function goWorkbench() {
  if (!project.value) return
  router.push(`/adaptation/workbench/${project.value.id}`)
}
</script>

<style scoped>
.adaptation-create { padding: 24px; max-width: 1000px; margin: 0 auto; }
.block { margin-bottom: 16px; }
.block-head { display: flex; justify-content: space-between; align-items: center; }
.block-actions { margin-top: 12px; display: flex; gap: 8px; }
.scene-preview { color: #606266; }
.footer-actions { display: flex; justify-content: center; padding: 16px 0; }
</style>
```

- [ ] **Step 2：build 检查**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3：提交**

```bash
git add frontend/src/views/AdaptationCreateView.vue
git commit -m "feat(adaptation): 创建页（导入/映射/强度/切场）"
```

---

## Task 14：工作台页 `AdaptationWorkbenchView.vue`

**Files:**
- Create: `frontend/src/views/AdaptationWorkbenchView.vue`

- [ ] **Step 1：实现（场列表 + 抽屉 + SSE 进度）**

```vue
<!-- frontend/src/views/AdaptationWorkbenchView.vue -->
<template>
  <div class="adaptation-wb">
    <div class="topbar">
      <div class="left">
        <h3>{{ project?.title || '...' }}</h3>
        <el-select v-if="versions.length" v-model="currentVid" size="small" style="width: 140px">
          <el-option v-for="v in versions" :key="v.id" :label="`v${v.version_no} (${v.status})`" :value="v.id" />
        </el-select>
      </div>
      <div class="right">
        <el-button :loading="running" @click="onFullRun">全场重跑</el-button>
        <el-button @click="onExport('txt')">导出 .txt</el-button>
        <el-button @click="onExport('docx')">导出 .docx</el-button>
      </div>
    </div>

    <div v-if="progress.total" class="progress">
      <el-progress :percentage="Math.round(progress.done / progress.total * 100)" :status="running ? '' : 'success'" />
      <span>{{ progress.done }} / {{ progress.total }} 场完成（失败 {{ progress.failed }}）</span>
    </div>

    <el-table :data="scenes" size="small" @row-click="openDrawer">
      <el-table-column label="#" width="60" prop="scene_index" />
      <el-table-column label="状态" width="100">
        <template #default="{row}">
          <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="场标题" prop="scene_title" />
      <el-table-column label="行数偏差" width="100">
        <template #default="{row}">
          <span v-if="row.line_count_delta_pct != null" :class="deltaClass(row)">
            {{ (row.line_count_delta_pct * 100).toFixed(0) }}%
          </span>
        </template>
      </el-table-column>
      <el-table-column label="" width="100">
        <template #default="{row}">
          <el-button link size="small" @click.stop="quickRerun(row)">重跑</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="drawerVisible" :title="`场 ${active?.scene_index ?? 0 + 1}`" size="80%" direction="btt">
      <el-tabs v-if="active" v-model="tab">
        <el-tab-pane label="原文" name="orig">
          <pre class="scene-text">{{ active.original_scene_text }}</pre>
        </el-tab-pane>
        <el-tab-pane label="改编后" name="new">
          <el-input v-model="editing" type="textarea" :rows="20" />
        </el-tab-pane>
        <el-tab-pane label="Diff" name="diff">
          <pre class="scene-text" v-html="diffHtml" />
        </el-tab-pane>
      </el-tabs>
      <template #footer>
        <div class="drawer-foot">
          <el-input v-model="extraPrompt" placeholder="（可选）本次重跑的额外提示词" style="flex: 1; margin-right: 8px" />
          <el-button @click="onRerun" :loading="rerunning">单场重跑</el-button>
          <el-button type="primary" @click="onSaveManual">保存手改</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { adaptationApi, type AdaptationProject, type AdaptationVersion, type SceneResult } from '@/api/adaptation'

const route = useRoute()
const projectId = Number(route.params.id)

const project = ref<AdaptationProject | null>(null)
const versions = ref<AdaptationVersion[]>([])
const currentVid = ref<number | null>(null)
const scenes = ref<SceneResult[]>([])
const running = ref(false)
const drawerVisible = ref(false)
const active = ref<SceneResult | null>(null)
const editing = ref('')
const extraPrompt = ref('')
const rerunning = ref(false)
const tab = ref('new')
let es: EventSource | null = null

const progress = computed(() => ({
  total: scenes.value.length,
  done: scenes.value.filter(s => s.status === 'done' || s.status === 'manual_edited').length,
  failed: scenes.value.filter(s => s.status === 'failed').length,
}))

const diffHtml = computed(() => {
  if (!active.value) return ''
  // 极简行级 diff：原+/改+ 不同就标
  const orig = (active.value.original_scene_text || '').split('\n')
  const cur = (active.value.rewritten_scene_text || '').split('\n')
  const max = Math.max(orig.length, cur.length)
  let html = ''
  for (let i = 0; i < max; i++) {
    const o = orig[i] ?? ''
    const c = cur[i] ?? ''
    if (o === c) html += `  ${escape(o)}\n`
    else {
      if (o) html += `<span style="color:#f56c6c">- ${escape(o)}</span>\n`
      if (c) html += `<span style="color:#67c23a">+ ${escape(c)}</span>\n`
    }
  }
  return html
})

function escape(s: string) {
  return s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]!))
}

function statusType(s: string) {
  if (s === 'done') return 'success'
  if (s === 'running') return 'warning'
  if (s === 'failed') return 'danger'
  if (s === 'manual_edited') return 'info'
  return ''
}

function deltaClass(row: SceneResult) {
  const pct = Math.abs((row.line_count_delta_pct ?? 0) * 100)
  if (!project.value) return ''
  const lim = project.value.intensity === 1 ? 0 : project.value.intensity === 2 ? 5 : 20
  return pct > lim ? 'delta-warn' : ''
}

async function loadProject() {
  const r = await adaptationApi.get(projectId)
  project.value = r.data
  versions.value = r.data.versions
  if (!currentVid.value && versions.value.length) {
    currentVid.value = Math.max(...versions.value.map(v => v.id))
  }
}

async function loadVersion() {
  if (!currentVid.value) { scenes.value = []; return }
  const r = await adaptationApi.getRun(currentVid.value)
  scenes.value = r.data.scene_results
  running.value = r.data.status === 'running'
  if (running.value) connectSSE()
}

watch(currentVid, loadVersion)

function connectSSE() {
  if (!currentVid.value) return
  closeSSE()
  es = new EventSource(adaptationApi.streamUrl(currentVid.value))
  es.onmessage = ev => {
    if (!ev.data) return
    let payload: any
    try { payload = JSON.parse(ev.data) } catch { return }
    if (payload.event === 'scene_done' || payload.event === 'scene_running') {
      const idx = scenes.value.findIndex(s => s.scene_index === payload.scene_index)
      if (idx >= 0) {
        if (payload.event === 'scene_running') scenes.value[idx].status = 'running'
        else {
          scenes.value[idx].status = payload.status
          scenes.value[idx].rewritten_scene_text = payload.rewritten
          scenes.value[idx].error = payload.error
          scenes.value[idx].line_count_delta_pct = payload.line_count_delta_pct
        }
      }
    }
    if (payload.event === 'version_done' || payload.event === 'version_failed') {
      running.value = false
      closeSSE()
      loadVersion()
      loadProject()
    }
  }
  es.onerror = () => { closeSSE(); setTimeout(() => running.value && loadVersion(), 1000) }
}

function closeSSE() { if (es) { es.close(); es = null } }

async function onFullRun() {
  if (!project.value) return
  running.value = true
  const r = await adaptationApi.createRun(project.value.id, extraPrompt.value || undefined)
  currentVid.value = r.data.id
  await loadProject()
  await loadVersion()
}

function openDrawer(row: SceneResult) {
  active.value = row
  editing.value = row.rewritten_scene_text || ''
  extraPrompt.value = ''
  tab.value = 'new'
  drawerVisible.value = true
}

async function onRerun() {
  if (!active.value || !currentVid.value) return
  rerunning.value = true
  try {
    const r = await adaptationApi.rerunScene(currentVid.value, active.value.scene_index, extraPrompt.value || undefined)
    active.value = r.data
    editing.value = r.data.rewritten_scene_text || ''
    const idx = scenes.value.findIndex(s => s.scene_index === r.data.scene_index)
    if (idx >= 0) scenes.value[idx] = r.data
    ElMessage.success('单场已重跑')
  } finally { rerunning.value = false }
}

async function quickRerun(row: SceneResult) {
  if (!currentVid.value) return
  active.value = row
  await onRerun()
}

async function onSaveManual() {
  if (!active.value || !currentVid.value) return
  const r = await adaptationApi.patchScene(currentVid.value, active.value.scene_index, editing.value)
  active.value = r.data
  const idx = scenes.value.findIndex(s => s.scene_index === r.data.scene_index)
  if (idx >= 0) scenes.value[idx] = r.data
  ElMessage.success('手改已保存')
}

function onExport(fmt: 'txt' | 'docx') {
  if (!currentVid.value) return
  window.open(adaptationApi.exportUrl(currentVid.value, fmt), '_blank')
}

onMounted(async () => { await loadProject(); await loadVersion() })
onUnmounted(closeSSE)
</script>

<style scoped>
.adaptation-wb { padding: 16px 24px; max-width: 1200px; margin: 0 auto; }
.topbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.topbar .left { display: flex; align-items: center; gap: 12px; }
.progress { margin: 8px 0 16px; display: flex; align-items: center; gap: 12px; }
.scene-text { white-space: pre-wrap; font-family: ui-monospace, monospace; font-size: 13px; line-height: 1.6; }
.delta-warn { color: #e6a23c; font-weight: 600; }
.drawer-foot { display: flex; align-items: center; }
</style>
```

- [ ] **Step 2：build 检查**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 3：提交**

```bash
git add frontend/src/views/AdaptationWorkbenchView.vue
git commit -m "feat(adaptation): 工作台页（场列表+抽屉 diff+手改+SSE 进度+全场重跑）"
```

---

## Task 15：路由 + 主菜单接入

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: 主菜单文件（参考 `App.vue` 或专门的导航组件——`grep -rn "我的剧本\|drama" frontend/src/components frontend/src/App.vue`）

- [ ] **Step 1：在 router 注册 3 个路由**

打开 `frontend/src/router/index.ts`，在 `/expansion` 系列附近追加：

```typescript
{
  path: '/adaptation',
  name: 'AdaptationList',
  component: () => import('@/views/AdaptationListView.vue'),
  meta: { title: '剧本改编', requiresAuth: true },
},
{
  path: '/adaptation/create',
  name: 'AdaptationCreate',
  component: () => import('@/views/AdaptationCreateView.vue'),
  meta: { title: '新建剧本改编', requiresAuth: true },
},
{
  path: '/adaptation/workbench/:id',
  name: 'AdaptationWorkbench',
  component: () => import('@/views/AdaptationWorkbenchView.vue'),
  meta: { title: '剧本改编工作台', requiresAuth: true },
},
```

- [ ] **Step 2：主菜单加入口**

```bash
grep -rn "我的剧本\|文本扩写\|/expansion" frontend/src/components frontend/src/App.vue 2>/dev/null
```

按定位到的菜单组件（多半是顶部 tabs 或侧栏），仿造 "文本扩写" 的菜单项追加 "剧本改编"：

```vue
<el-menu-item index="/adaptation" @click="$router.push('/adaptation')">剧本改编</el-menu-item>
```

- [ ] **Step 3：build 检查**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

- [ ] **Step 4：提交**

```bash
git add frontend/src/router/index.ts frontend/src/components frontend/src/App.vue
git commit -m "feat(adaptation): 路由与主菜单接入"
```

---

## Task 16：端到端手测 + 收尾

**Files:**
- 不改代码；执行以下手测清单。

- [ ] **Step 1：启动栈**

```bash
docker compose up --build -d
```

等容器健康；前端 http://localhost:3000，API http://localhost:8000/docs

- [ ] **Step 2：手测清单（每项打钩前必须实测通过）**

- [ ] 登录后菜单出现「剧本改编」入口
- [ ] /adaptation 列表为空时显示空态
- [ ] /adaptation/create 粘贴文本路径：填标题→粘 200 字内文本→选强度 2→点"创建项目"
- [ ] /adaptation/create 上传路径：拖入 `drama/解说漫：买榴莲.txt` 创建
- [ ] 实体抽取按钮：点完后表中至少出现 1 行
- [ ] 修改一行 replacement_text，勾上 locked，点保存映射
- [ ] AI 建议替换：点完后空 replacement 被填充
- [ ] 切场：点"开始切场"，看到场列表
- [ ] 重新切场可以重复执行
- [ ] 进入工作台：场列表渲染正确
- [ ] "全场重跑"开始后，顶部进度条出现，场状态点逐场亮绿（SSE 推送生效）
- [ ] 跑完后总状态变为 done，新版本写入 versions 列表
- [ ] 点击单场打开抽屉：原文 / 改编后 / Diff 三个 tab 都有内容
- [ ] 在改编后 tab 改一两个字 → 保存手改 → 列表对应行变 manual_edited 黄色 tag
- [ ] 单场重跑（带 extra_prompt） → 该场状态变化、内容刷新
- [ ] 导出 .txt → 浏览器下载，内容是 N 场拼接
- [ ] 导出 .docx → 浏览器下载，可在 Word/WPS 打开
- [ ] 切换到旧版本 → 工作台展示对应版本的 scenes
- [ ] 删除项目（列表页删按钮） → 列表刷新且 DB 中级联删除

- [ ] **Step 3：跑全部后端测试确认无回归**

```bash
cd backend && pytest -v 2>&1 | tail -40
```
Expected: 全绿（含本次新增的 5 个测试文件）

- [ ] **Step 4：CHANGELOG 追加**

打开 `CHANGELOG.md`，在文件顶部 `## [1.3.0]` 上方插入：

```markdown
## [1.4.0] - 2026-05-11

### Added
- 剧本改编模块：导入剧本后改人名/地名/道具/时代背景，剧情节奏不变
  - 三档改编强度（替换/润色/重铸）
  - AI 自动抽实体表 + 用户编辑 + 锁定行
  - 按场切分（正则优先 LLM fallback）
  - 并发分场改写 + SSE 进度推送
  - 场列表 + 抽屉 diff + 手改 + 单场/全场重跑
  - 多版本管理 + 一键导出 txt/docx
```

- [ ] **Step 5：提交收尾**

```bash
git add CHANGELOG.md
git commit -m "chore: 1.4.0 changelog 标记剧本改编模块上线"
```

---

## 实施 PR / 后续

- 全部 16 个任务完成后，本分支处于 release-ready 状态。
- v2 待办（参考 spec §10）：节奏校验、多版本对比视图、跨项目实体库、多 worker 化（迁 Redis）、转 ScriptProject 链路。
