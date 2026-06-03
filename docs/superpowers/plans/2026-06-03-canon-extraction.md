# 原作设定提取子系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给定一部原作小说，用 LLM 分块提取 + 分层归并消歧，产出可溯源、可人工校对的设定圣经(canon)，挂在 ReferenceNovel 上跨项目复用，并供 wizard 二创创作锚定。

**Architecture:** 套用现有 `prose_pipeline` 范式——异步 pipeline（CHUNK→ATOMIC_EXTRACT→MERGE_DISAMBIGUATE→PERSIST）+ `event_bus` SSE 进度 + status 状态机 + 子行表。新增 2 张表（`canon_entity` 多态实体 + `canon_extraction_job` 任务），复用 `ChunkService`、`AIService.generate_text`、`_extract_json` 容错。

**Tech Stack:** Python FastAPI + SQLAlchemy 2.0(async) + SQLite/PG + pytest-asyncio；前端 Vue3 + TS + Element Plus。建表靠 `Base.metadata.create_all`（**无 alembic**，注册进 `models/__init__.py` 即可）。

**关键参考文件（实施前先读）:**
- `backend/app/services/prose_pipeline.py` — pipeline 编排 + gather 容错范式
- `backend/app/services/prose_event_bus.py` — SSE 事件总线（直接照抄改名）
- `backend/app/routers/prose.py` — SSE ticket + stream 端点范式
- `backend/app/models/prose_project.py` — 模型+状态机写法
- `backend/app/services/chunk.py::ChunkService.split_text` — 复用分块
- `backend/app/services/ai_service.py::AIService.generate_text(prompt, provider, max_tokens)` — LLM 调用
- `backend/app/routers/wizard.py:97-113` — 现有 reference 作 style_reference 的注入点
- `backend/tests/test_prose_pipeline.py` / `test_prose_models.py` / `test_prose_router.py` — 测试范式

---

## Task 1: 数据模型 canon_entity + canon_extraction_job

**Files:**
- Create: `backend/app/models/canon.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_canon_models.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_models.py`:

```python
"""canon 模型测试：建表 + 字段默认值 + JSON 往返"""
import pytest
from sqlalchemy import select

from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.reference import ReferenceNovel


@pytest.fixture
async def ref(db_session):
    r = ReferenceNovel(title="西游记", total_chars=1000)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_create_canon_entity_with_json_fields(db_session, ref):
    e = CanonEntity(
        reference_id=ref.id,
        entity_type="character",
        canonical_name="乌鸡国国王",
        aliases=["陛下", "那妖道假扮的国王"],
        summary="被狮猁怪推入井中三年的乌鸡国君主",
        attributes={"role": "受害君主", "fate": "被青毛狮子精顶替"},
        source_refs=[{"chapter": "第三十七回", "offset": 1200, "quote": "我本是乌鸡国王"}],
        importance="major",
        confidence=0.9,
    )
    db_session.add(e)
    await db_session.commit()
    await db_session.refresh(e)

    assert e.id is not None
    assert e.review_status == "ai_extracted"  # 默认值
    assert e.aliases == ["陛下", "那妖道假扮的国王"]
    assert e.source_refs[0]["chapter"] == "第三十七回"


async def test_create_extraction_job_defaults(db_session, ref):
    job = CanonExtractionJob(reference_id=ref.id, model="demo")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    assert job.status == "pending"
    assert job.chunk_total == 0
    assert job.chunk_done == 0
    assert job.failed_chunks == 0
    assert job.entity_count == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.canon'`

- [ ] **Step 3: 写模型实现**

Create `backend/app/models/canon.py`:

```python
"""原作设定 canon 模型：挂在 ReferenceNovel 上，跨项目复用。
- CanonEntity: 多态设定条目（角色/地点/能力/势力/世界观规则/事件）
- CanonExtractionJob: 提取任务，状态机 + 进度计数（仿 ProseProject）
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CanonEntity(Base):
    """原作设定条目（多态）"""
    __tablename__ = "canon_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("reference_novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # character / location / ability / faction / worldrule / event
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # 溯源：[{"chapter":..,"offset":..,"quote":".."}]
    source_refs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    importance: Mapped[str] = mapped_column(String(20), default="major")  # critical/major/minor
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # ai_extracted / user_verified / user_edited / user_added
    review_status: Mapped[str] = mapped_column(String(20), default="ai_extracted")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class CanonExtractionJob(Base):
    """设定提取任务"""
    __tablename__ = "canon_extraction_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("reference_novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/done/failed
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    chunk_total: Mapped[int] = mapped_column(Integer, default=0)
    chunk_done: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())
```

- [ ] **Step 4: 注册模型**

Modify `backend/app/models/__init__.py` — 在 `from app.models.prose_project import ProseProject, ProseScene` 之后加一行：

```python
from app.models.canon import CanonEntity, CanonExtractionJob
```

并在 `__all__` 列表末尾（`"ProseProject", "ProseScene",` 之后）加：

```python
    "CanonEntity", "CanonExtractionJob",
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_models.py -v`
Expected: PASS（2 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/canon.py backend/app/models/__init__.py backend/tests/test_canon_models.py
git commit -m "feat(canon): canon_entity + canon_extraction_job 模型"
```

---

## Task 2: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/canon.py`
- Test: `backend/tests/test_canon_schemas.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_schemas.py`:

```python
"""canon schema 序列化测试"""
from app.schemas.canon import (
    CanonEntityOut, CanonEntityCreate, CanonEntityUpdate, CanonJobOut,
)


def test_entity_create_requires_type_and_name():
    c = CanonEntityCreate(entity_type="character", canonical_name="孙悟空")
    assert c.entity_type == "character"
    assert c.aliases == []
    assert c.attributes == {}


def test_entity_update_all_optional():
    u = CanonEntityUpdate(summary="改过的设定")
    assert u.summary == "改过的设定"
    assert u.canonical_name is None


def test_job_out_from_attributes():
    class FakeJob:
        id = 1
        reference_id = 2
        status = "done"
        model = "demo"
        chunk_total = 5
        chunk_done = 5
        failed_chunks = 0
        entity_count = 12
        error = None
        created_at = None
        updated_at = None
    out = CanonJobOut.model_validate(FakeJob())
    assert out.entity_count == 12
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas.canon'`

- [ ] **Step 3: 写 schema 实现**

Create `backend/app/schemas/canon.py`:

```python
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class CanonEntityOut(BaseModel):
    id: int
    reference_id: int
    entity_type: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    importance: str
    confidence: float
    review_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CanonEntityCreate(BaseModel):
    entity_type: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    importance: str = "major"


class CanonEntityUpdate(BaseModel):
    canonical_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    summary: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    importance: Optional[str] = None
    review_status: Optional[str] = None


class CanonJobOut(BaseModel):
    id: int
    reference_id: int
    status: str
    model: Optional[str] = None
    chunk_total: int
    chunk_done: int
    failed_chunks: int
    entity_count: int
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
```

> 注意：`model` 字段名与 Pydantic 的 `model_` 前缀保护无冲突（保护的是 `model_config`/`model_validate` 等方法，普通字段 `model` 可用），但若运行报 warning，加 `model_config = ConfigDict(protected_namespaces=())`。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_schemas.py -v`
Expected: PASS（3 passed）。若出现 `model` 字段 warning，按 Step 3 注释加 `protected_namespaces=()` 后重跑。

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas/canon.py backend/tests/test_canon_schemas.py
git commit -m "feat(canon): pydantic schemas"
```

---

## Task 3: canon_event_bus（SSE 事件总线）

**Files:**
- Create: `backend/app/services/canon_event_bus.py`
- Test: `backend/tests/test_canon_event_bus.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_event_bus.py`:

```python
"""canon_event_bus：subscribe/publish/unsubscribe，按 reference_id 分组"""
import pytest
from app.services.canon_event_bus import canon_event_bus


async def test_publish_reaches_subscriber():
    sub = canon_event_bus.subscribe(reference_id=42)
    await canon_event_bus.publish(42, {"event": "progress", "chunk_done": 1})
    msg = sub.queue.get_nowait()
    assert msg["event"] == "progress"
    canon_event_bus.unsubscribe(sub)


async def test_unsubscribe_removes_bucket():
    sub = canon_event_bus.subscribe(reference_id=7)
    canon_event_bus.unsubscribe(sub)
    # 再 publish 不应抛错（无订阅者）
    await canon_event_bus.publish(7, {"event": "done"})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_event_bus.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 写实现（照抄 prose_event_bus，project_id→reference_id）**

Create `backend/app/services/canon_event_bus.py`:

```python
"""单进程内的 reference 级事件总线，用于 canon 提取 SSE 推送。
与 prose_event_bus 相同模式，按 reference_id 分组。
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Set


@dataclass(eq=False)
class _Subscriber:
    reference_id: int
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    _uid: int = field(default_factory=lambda: id(object()), repr=False)

    def __hash__(self) -> int:
        return self._uid

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Subscriber) and self._uid == other._uid


class _EventBus:
    def __init__(self) -> None:
        self._subs: Dict[int, Set[_Subscriber]] = {}

    def subscribe(self, reference_id: int) -> _Subscriber:
        sub = _Subscriber(reference_id=reference_id)
        self._subs.setdefault(reference_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: _Subscriber) -> None:
        bucket = self._subs.get(sub.reference_id)
        if bucket and sub in bucket:
            bucket.remove(sub)
            if not bucket:
                self._subs.pop(sub.reference_id, None)

    async def publish(self, reference_id: int, payload: Dict[str, Any]) -> None:
        for sub in list(self._subs.get(reference_id, ())):
            try:
                sub.queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    sub.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                sub.queue.put_nowait(payload)


canon_event_bus = _EventBus()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_event_bus.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_event_bus.py backend/tests/test_canon_event_bus.py
git commit -m "feat(canon): canon_event_bus SSE 事件总线"
```

---

## Task 4: 提取 prompts（原子提取 + 归并消歧）

**Files:**
- Create: `backend/app/services/canon_prompts.py`
- Test: `backend/tests/test_canon_prompts.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_prompts.py`:

```python
"""canon prompts：模板渲染含必填指令"""
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt


def test_atomic_prompt_contains_chunk_and_sourcing_rule():
    p = build_atomic_prompt(chunk_text="乌鸡国国王被推入井中。", chunk_label="第三十七回")
    assert "乌鸡国国王被推入井中" in p
    assert "第三十七回" in p
    assert "quote" in p          # 要求附原文引用
    assert "JSON" in p


def test_merge_prompt_groups_by_type():
    raw = [
        {"entity_type": "character", "canonical_name": "乌鸡国王", "aliases": ["陛下"]},
        {"entity_type": "character", "canonical_name": "乌鸡国国王", "aliases": []},
    ]
    p = build_merge_prompt(entity_type="character", raw_entities=raw)
    assert "乌鸡国王" in p
    assert "乌鸡国国王" in p
    assert "合并" in p or "归并" in p
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 写 prompts 实现**

Create `backend/app/services/canon_prompts.py`:

```python
"""原作设定提取 prompts：原子提取 + 跨块归并消歧。
设计要点（对应 spec 准确度三难点）：
- 原子提取强制每条设定附原文 quote + 章节定位（溯源/防幻觉）
- 归并按 entity_type 分组，要求消歧同一实体的不同称呼
"""
import json

ENTITY_TYPES_CN = {
    "character": "角色（人物）",
    "location": "地点（地名/场所）",
    "ability": "能力（功法/法术/法宝/技能）",
    "faction": "势力（门派/国家/组织）",
    "worldrule": "世界观规则（修炼体系/天道法则/社会设定）",
    "event": "关键事件（推动剧情的重大事件）",
}

ATOMIC_SYSTEM = """你是一位严谨的原作设定分析专家。请从给定的小说片段中，只提取【本片段明确出现】的设定信息，分为六类：
角色(character)/地点(location)/能力(ability)/势力(faction)/世界观规则(worldrule)/关键事件(event)。

【铁律——防止幻觉】
1. 只提取片段中【确有文字依据】的设定，严禁脑补、严禁补充原作其他章节的知识。
2. 每一条设定都必须附带 source（原文引用片段 quote，≤40字，从片段中原样摘录）。
3. 无法确定的字段留空，不要编造。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "character|location|ability|faction|worldrule|event",
  "canonical_name": "设定名",
  "aliases": ["别名/称呼"],
  "summary": "一句话设定（仅依据本片段）",
  "attributes": {"任意键": "值"},
  "source": {"quote": "原文摘录≤40字"},
  "importance": "critical|major|minor"
}
只输出 JSON 数组，不要任何解释文字。"""

MERGE_SYSTEM = """你是一位严谨的原作设定归并专家。下面是从同一部原作不同片段提取的【同一类型】设定条目，其中可能有重复或指代同一对象的不同称呼。

【任务】
1. 把指代同一对象的条目【归并为一条】：选最正式的名字作 canonical_name，其余称呼并入 aliases。
2. 合并各条目的 attributes（冲突时保留更具体的，并在 summary 注明）。
3. 保留所有来源 source 到 source_refs 数组，不得丢弃。
4. 严禁新增原文没有的设定。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "<与输入相同>",
  "canonical_name": "权威名",
  "aliases": ["所有别名"],
  "summary": "综合一句话设定",
  "attributes": {...},
  "source_refs": [{"quote": "..."}, ...],
  "importance": "critical|major|minor"
}
只输出 JSON 数组，不要任何解释文字。"""


def build_atomic_prompt(chunk_text: str, chunk_label: str) -> str:
    return (
        f"{ATOMIC_SYSTEM}\n\n"
        f"【片段位置】{chunk_label}\n"
        f"【片段正文】\n{chunk_text}\n\n"
        f"请输出本片段的设定 JSON 数组（每条含 source.quote 原文引用）："
    )


def build_merge_prompt(entity_type: str, raw_entities: list) -> str:
    type_cn = ENTITY_TYPES_CN.get(entity_type, entity_type)
    payload = json.dumps(raw_entities, ensure_ascii=False, indent=2)
    return (
        f"{MERGE_SYSTEM}\n\n"
        f"【设定类型】{type_cn}（{entity_type}）\n"
        f"【待归并条目】\n{payload}\n\n"
        f"请输出归并消歧后的 JSON 数组："
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_prompts.py backend/tests/test_canon_prompts.py
git commit -m "feat(canon): 原子提取+归并消歧 prompts"
```

---

## Task 5: pipeline 之 CHUNK 阶段 + JSON 容错工具

**Files:**
- Create: `backend/app/services/canon_pipeline.py`
- Test: `backend/tests/test_canon_pipeline.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_pipeline.py`:

```python
"""canon_pipeline 纯函数单测（不触发 LLM）"""
from app.services.canon_pipeline import _chunk_reference, _safe_json_array


def test_chunk_reference_splits_long_text():
    content = "\n".join([f"第{i}段内容，约二十个汉字凑数填充。" for i in range(50)])
    chunks = _chunk_reference(content, chunk_size=200)
    assert len(chunks) > 1
    # 每块带 label
    assert all("label" in c and "text" in c for c in chunks)
    assert chunks[0]["label"].startswith("片段")


def test_safe_json_array_parses_fenced():
    raw = '```json\n[{"canonical_name":"孙悟空","entity_type":"character"}]\n```'
    arr = _safe_json_array(raw)
    assert len(arr) == 1
    assert arr[0]["canonical_name"] == "孙悟空"


def test_safe_json_array_returns_empty_on_garbage():
    assert _safe_json_array("这不是JSON，纯文本。") == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 写 CHUNK + JSON 容错实现**

Create `backend/app/services/canon_pipeline.py`:

```python
# backend/app/services/canon_pipeline.py
"""原作设定提取 pipeline：CHUNK → ATOMIC_EXTRACT → MERGE_DISAMBIGUATE → PERSIST。

套用 prose_pipeline 范式：asyncio.gather 并行 + return_exceptions 容错 +
canon_event_bus SSE 进度 + CanonExtractionJob 状态机。
"""
import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.chunk import ChunkService
from app.services.ai_service import AIService
from app.services.canon_event_bus import canon_event_bus
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt
from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.reference import ReferenceNovel

logger = logging.getLogger(__name__)

ENTITY_TYPES = ["character", "location", "ability", "faction", "worldrule", "event"]
ATOMIC_CONCURRENCY = 4   # 并行块数上限
MERGE_BATCH = 40         # 单次归并的最大条目数（树状分批）


def _chunk_reference(content: str, chunk_size: int = 4000) -> List[Dict[str, str]]:
    """复用 ChunkService.split_text，给每块加上「片段N」label。"""
    raw_chunks = ChunkService.split_text(content, chunk_size=chunk_size, overlap=200)
    return [
        {"label": f"片段{i + 1}", "text": text}
        for i, text in enumerate(raw_chunks)
    ]


def _safe_json_array(text: str) -> List[Dict[str, Any]]:
    """从 LLM 输出中稳健提取 JSON 数组（容错 ```json 围栏、前后噪声）。
    仿 wizard._extract_json_array。失败返回 []。
    """
    if not text:
        return []
    # 去掉 markdown 围栏
    text = re.sub(r"```(?:json)?", "", text).strip()
    # 找第一个 [ 到匹配的 ]
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start:i + 1])
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
    return []
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_pipeline.py
git commit -m "feat(canon): pipeline CHUNK 阶段 + JSON 容错"
```

---

## Task 6: pipeline 之 ATOMIC_EXTRACT 阶段

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`
- Test: `backend/tests/test_canon_pipeline.py`（追加）

- [ ] **Step 1: 追加失败测试**

Append to `backend/tests/test_canon_pipeline.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock


async def test_atomic_extract_one_chunk_parses_entities():
    from app.services.canon_pipeline import _atomic_extract_chunk

    fake_llm = AsyncMock(return_value=(
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source":{"quote":"我本是乌鸡国王"},"importance":"major"}]'
    ))
    with patch.object(AIService, "generate_text", fake_llm):
        ents = await _atomic_extract_chunk(
            {"label": "第三十七回", "text": "我本是乌鸡国王..."}, model=None
        )
    assert len(ents) == 1
    assert ents[0]["canonical_name"] == "乌鸡国国王"
    # source 被规整进 source_refs
    assert ents[0]["source_refs"][0]["quote"] == "我本是乌鸡国王"
    assert ents[0]["source_refs"][0]["chapter"] == "第三十七回"


async def test_atomic_extract_chunk_handles_bad_json():
    from app.services.canon_pipeline import _atomic_extract_chunk
    with patch.object(AIService, "generate_text", AsyncMock(return_value="抱歉我无法解析")):
        ents = await _atomic_extract_chunk({"label": "片段1", "text": "x"}, model=None)
    assert ents == []
```

需要在文件顶部已 import `AIService`（Task 5 已 import）。

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -k atomic -v`
Expected: FAIL — `cannot import name '_atomic_extract_chunk'`

- [ ] **Step 3: 实现 _atomic_extract_chunk**

Append to `backend/app/services/canon_pipeline.py`:

```python
async def _atomic_extract_chunk(chunk: Dict[str, str], model: Optional[str]) -> List[Dict[str, Any]]:
    """单块原子提取：调 LLM → 解析 → 把 source.quote 规整为 source_refs（附 chapter=label）。
    任何异常/坏 JSON 返回 []（由上层计 failed）。
    """
    prompt = build_atomic_prompt(chunk_text=chunk["text"], chunk_label=chunk["label"])
    raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
    entities = _safe_json_array(raw)

    normalized: List[Dict[str, Any]] = []
    for e in entities:
        if not isinstance(e, dict) or not e.get("canonical_name"):
            continue
        src = e.pop("source", None) or {}
        quote = src.get("quote") if isinstance(src, dict) else None
        e["source_refs"] = [{"chapter": chunk["label"], "quote": quote}] if quote else []
        e.setdefault("aliases", [])
        e.setdefault("attributes", {})
        e.setdefault("importance", "major")
        normalized.append(e)
    return normalized
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -k atomic -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_pipeline.py
git commit -m "feat(canon): ATOMIC_EXTRACT 单块提取+溯源规整"
```

---

## Task 7: pipeline 之 MERGE_DISAMBIGUATE 阶段

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`
- Test: `backend/tests/test_canon_pipeline.py`（追加）

- [ ] **Step 1: 追加失败测试**

Append to `backend/tests/test_canon_pipeline.py`:

```python
async def test_merge_entities_by_type_disambiguates():
    from app.services.canon_pipeline import _merge_entities_of_type

    raw = [
        {"entity_type": "character", "canonical_name": "乌鸡国王",
         "aliases": ["陛下"], "source_refs": [{"chapter": "片段1", "quote": "a"}]},
        {"entity_type": "character", "canonical_name": "乌鸡国国王",
         "aliases": [], "source_refs": [{"chapter": "片段2", "quote": "b"}]},
    ]
    merged_json = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下","乌鸡国王"],"summary":"被害君主",'
        '"source_refs":[{"chapter":"片段1","quote":"a"},{"chapter":"片段2","quote":"b"}],'
        '"importance":"major"}]'
    )
    with patch.object(AIService, "generate_text", AsyncMock(return_value=merged_json)):
        merged = await _merge_entities_of_type("character", raw, model=None)
    assert len(merged) == 1
    assert merged[0]["canonical_name"] == "乌鸡国国王"
    assert len(merged[0]["source_refs"]) == 2


async def test_merge_entities_empty_returns_empty():
    from app.services.canon_pipeline import _merge_entities_of_type
    assert await _merge_entities_of_type("ability", [], model=None) == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -k merge -v`
Expected: FAIL — `cannot import name '_merge_entities_of_type'`

- [ ] **Step 3: 实现 _merge_entities_of_type（含树状分批）**

Append to `backend/app/services/canon_pipeline.py`:

```python
async def _merge_entities_of_type(
    entity_type: str, raw_entities: List[Dict[str, Any]], model: Optional[str]
) -> List[Dict[str, Any]]:
    """对同类型条目做 LLM 归并消歧。条目过多时树状分批（每批 MERGE_BATCH）。"""
    if not raw_entities:
        return []
    if len(raw_entities) <= MERGE_BATCH:
        prompt = build_merge_prompt(entity_type, raw_entities)
        raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
        merged = _safe_json_array(raw)
        # 回退：归并失败则原样返回（不丢数据）
        return merged if merged else raw_entities

    # 分批归并后递归再归并
    batch_results: List[Dict[str, Any]] = []
    for i in range(0, len(raw_entities), MERGE_BATCH):
        batch = raw_entities[i:i + MERGE_BATCH]
        prompt = build_merge_prompt(entity_type, batch)
        raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
        batch_results.extend(_safe_json_array(raw) or batch)
    return await _merge_entities_of_type(entity_type, batch_results, model)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -k merge -v`
Expected: PASS（2 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_pipeline.py
git commit -m "feat(canon): MERGE_DISAMBIGUATE 归并消歧+树状分批"
```

---

## Task 8: pipeline 编排 run_canon_extraction（串联+落库+SSE+状态机）

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`
- Test: `backend/tests/test_canon_pipeline.py`（追加端到端）

- [ ] **Step 1: 追加端到端失败测试**

Append to `backend/tests/test_canon_pipeline.py`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity, CanonExtractionJob
from sqlalchemy import select


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def test_run_canon_extraction_end_to_end(db_session, session_factory):
    ref = ReferenceNovel(title="测试原作",
                         content="乌鸡国国王被狮猁怪推入御花园八角琉璃井中。" * 30,
                         total_chars=600)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)

    atomic_out = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source":{"quote":"乌鸡国国王被推入井中"},"importance":"major"}]'
    )
    merge_out = (
        '[{"entity_type":"character","canonical_name":"乌鸡国国王",'
        '"aliases":["陛下"],"summary":"被害君主",'
        '"source_refs":[{"chapter":"片段1","quote":"乌鸡国国王被推入井中"}],'
        '"importance":"major"}]'
    )

    async def fake_generate(prompt, provider=None, max_tokens=None):
        return merge_out if "归并" in prompt or "待归并" in prompt else atomic_out

    from app.services.canon_pipeline import run_canon_extraction
    with patch.object(AIService, "generate_text", side_effect=fake_generate):
        job_id = await run_canon_extraction(ref.id, session_factory, model="demo")

    async with session_factory() as s:
        job = (await s.execute(select(CanonExtractionJob).where(
            CanonExtractionJob.id == job_id))).scalar_one()
        assert job.status == "done"
        assert job.entity_count >= 1
        ents = (await s.execute(select(CanonEntity).where(
            CanonEntity.reference_id == ref.id))).scalars().all()
        assert any(e.canonical_name == "乌鸡国国王" for e in ents)
        assert ents[0].source_refs  # 溯源非空（准确度回归基线）
        assert ents[0].review_status == "ai_extracted"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -k end_to_end -v`
Expected: FAIL — `cannot import name 'run_canon_extraction'`

- [ ] **Step 3: 实现编排函数**

Append to `backend/app/services/canon_pipeline.py`:

```python
async def run_canon_extraction(
    reference_id: int,
    session_factory: async_sessionmaker,
    model: Optional[str] = None,
) -> int:
    """编排：建 job → CHUNK → ATOMIC(并行) → MERGE(按类型) → PERSIST。返回 job_id。
    幂等：重跑前清空该 reference 既有 ai_extracted 实体（保留 user_* 人工条目）。
    """
    # 1) 建 job + 取原作正文
    async with session_factory() as s:
        ref = (await s.execute(select(ReferenceNovel).where(
            ReferenceNovel.id == reference_id))).scalar_one_or_none()
        if ref is None:
            raise ValueError(f"reference {reference_id} 不存在")
        content = ref.content or ""
        job = CanonExtractionJob(reference_id=reference_id, model=model, status="processing")
        s.add(job)
        await s.commit()
        await s.refresh(job)
        job_id = job.id

    try:
        # 2) CHUNK
        chunks = _chunk_reference(content)
        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.chunk_total = len(chunks)
            await s.commit()
        await canon_event_bus.publish(reference_id,
            {"event": "chunked", "chunk_total": len(chunks)})

        # 3) ATOMIC（并行限流）
        sem = asyncio.Semaphore(ATOMIC_CONCURRENCY)
        done = 0
        failed = 0
        all_atomic: List[Dict[str, Any]] = []

        async def _worker(ch):
            async with sem:
                return await _atomic_extract_chunk(ch, model)

        results = await asyncio.gather(*[_worker(c) for c in chunks],
                                       return_exceptions=True)
        for r in results:
            if isinstance(r, Exception):
                failed += 1
                logger.warning("canon atomic chunk failed: %s", r)
            else:
                all_atomic.extend(r)
            done += 1
            await canon_event_bus.publish(reference_id,
                {"event": "progress", "chunk_done": done, "failed": failed})

        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.chunk_done = done
            j.failed_chunks = failed
            await s.commit()

        # 4) MERGE（按类型）
        by_type: Dict[str, List[Dict[str, Any]]] = {t: [] for t in ENTITY_TYPES}
        for e in all_atomic:
            t = e.get("entity_type")
            if t in by_type:
                by_type[t].append(e)
        merged_all: List[Dict[str, Any]] = []
        for t in ENTITY_TYPES:
            merged_all.extend(await _merge_entities_of_type(t, by_type[t], model))
        await canon_event_bus.publish(reference_id,
            {"event": "merged", "entity_count": len(merged_all)})

        # 5) PERSIST（先清旧 ai_extracted，保留人工条目）
        async with session_factory() as s:
            await s.execute(delete(CanonEntity).where(
                CanonEntity.reference_id == reference_id,
                CanonEntity.review_status == "ai_extracted"))
            for e in merged_all:
                s.add(CanonEntity(
                    reference_id=reference_id,
                    entity_type=e.get("entity_type", "character"),
                    canonical_name=e.get("canonical_name", "")[:200] or "未命名",
                    aliases=e.get("aliases", []),
                    summary=e.get("summary"),
                    attributes=e.get("attributes", {}),
                    source_refs=e.get("source_refs", []),
                    importance=e.get("importance", "major"),
                    confidence=float(e.get("confidence", 1.0)),
                    review_status="ai_extracted",
                ))
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.entity_count = len(merged_all)
            j.status = "done"
            await s.commit()

        await canon_event_bus.publish(reference_id,
            {"event": "done", "entity_count": len(merged_all)})
        return job_id

    except Exception as exc:  # noqa: BLE001
        logger.exception("canon extraction failed")
        async with session_factory() as s:
            j = (await s.execute(select(CanonExtractionJob).where(
                CanonExtractionJob.id == job_id))).scalar_one()
            j.status = "failed"
            j.error = str(exc)[:2000]
            await s.commit()
        await canon_event_bus.publish(reference_id, {"event": "failed", "error": str(exc)})
        return job_id
```

- [ ] **Step 4: 运行确认通过（含全文件回归）**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py -v`
Expected: PASS（全部，含 end_to_end）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_pipeline.py
git commit -m "feat(canon): run_canon_extraction 编排+落库+SSE+状态机"
```

---

## Task 9: canon router（启动提取/查任务/CRUD 实体/SSE）

**Files:**
- Create: `backend/app/routers/canon.py`
- Modify: `backend/app/main.py:40`（import）、`:147`（include）
- Test: `backend/tests/test_canon_router.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_router.py`:

```python
"""canon router：启动提取（mock pipeline）+ 实体 CRUD"""
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select

from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity


@pytest.fixture
async def ref(db_session, sample_user):
    r = ReferenceNovel(title="原作A", owner_id=sample_user.id, content="正文", total_chars=10)
    db_session.add(r)
    await db_session.commit()
    await db_session.refresh(r)
    return r


async def test_list_entities_empty(client, ref):
    resp = await client.get(f"/api/v1/references/{ref.id}/canon/entities")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_create_and_update_and_delete_entity(client, ref):
    # 手动新增
    r = await client.post(f"/api/v1/references/{ref.id}/canon/entities",
        json={"entity_type": "character", "canonical_name": "孙悟空"})
    assert r.status_code == 201
    eid = r.json()["id"]
    assert r.json()["review_status"] == "user_added"

    # 更新
    r2 = await client.put(f"/api/v1/references/{ref.id}/canon/entities/{eid}",
        json={"summary": "齐天大圣"})
    assert r2.status_code == 200
    assert r2.json()["summary"] == "齐天大圣"
    assert r2.json()["review_status"] == "user_edited"

    # 删除
    r3 = await client.delete(f"/api/v1/references/{ref.id}/canon/entities/{eid}")
    assert r3.status_code == 204


async def test_start_extraction_triggers_pipeline(client, ref):
    with patch("app.routers.canon.run_canon_extraction",
               new=AsyncMock(return_value=123)) as m:
        with patch("app.routers.canon.asyncio.create_task") as ct:
            resp = await client.post(f"/api/v1/references/{ref.id}/canon/extract")
    assert resp.status_code == 202
    assert ct.called  # 后台任务被调度
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_router.py -v`
Expected: FAIL — 404（路由未注册）

- [ ] **Step 3: 写 router 实现**

Create `backend/app/routers/canon.py`:

```python
"""原作设定 canon 路由：提取触发 + 任务查询 + 实体 CRUD + SSE。
挂在 /api/v1/references/{reference_id}/canon 下。
"""
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db, engine
from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity, CanonExtractionJob
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.canon import (
    CanonEntityOut, CanonEntityCreate, CanonEntityUpdate, CanonJobOut,
)
from app.services.canon_pipeline import run_canon_extraction
from app.services.canon_event_bus import canon_event_bus

router = APIRouter(prefix="/api/v1/references/{reference_id}/canon", tags=["canon"])


async def _get_owned_ref(reference_id: int, db: AsyncSession, user: User) -> ReferenceNovel:
    ref = (await db.execute(select(ReferenceNovel).where(
        ReferenceNovel.id == reference_id,
        (ReferenceNovel.owner_id == user.id) | (ReferenceNovel.owner_id == None),  # noqa: E711
    ))).scalar_one_or_none()
    if ref is None:
        raise HTTPException(status_code=404, detail="原作不存在")
    return ref


@router.post("/extract", status_code=202)
async def start_extraction(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.create_task(run_canon_extraction(reference_id, session_factory))
    return {"message": "提取已启动", "reference_id": reference_id}


@router.get("/job", response_model=CanonJobOut)
async def latest_job(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    job = (await db.execute(select(CanonExtractionJob).where(
        CanonExtractionJob.reference_id == reference_id
    ).order_by(CanonExtractionJob.id.desc()).limit(1))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="尚无提取任务")
    return job


@router.get("/entities", response_model=list[CanonEntityOut])
async def list_entities(
    reference_id: int,
    entity_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    stmt = select(CanonEntity).where(CanonEntity.reference_id == reference_id)
    if entity_type:
        stmt = stmt.where(CanonEntity.entity_type == entity_type)
    rows = (await db.execute(stmt.order_by(CanonEntity.entity_type, CanonEntity.id))).scalars().all()
    return rows


@router.post("/entities", response_model=CanonEntityOut, status_code=201)
async def create_entity(
    reference_id: int,
    payload: CanonEntityCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = CanonEntity(
        reference_id=reference_id,
        entity_type=payload.entity_type,
        canonical_name=payload.canonical_name,
        aliases=payload.aliases,
        summary=payload.summary,
        attributes=payload.attributes,
        source_refs=payload.source_refs,
        importance=payload.importance,
        review_status="user_added",
    )
    db.add(e)
    await db.commit()
    await db.refresh(e)
    return e


@router.put("/entities/{entity_id}", response_model=CanonEntityOut)
async def update_entity(
    reference_id: int,
    entity_id: int,
    payload: CanonEntityUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = (await db.execute(select(CanonEntity).where(
        CanonEntity.id == entity_id,
        CanonEntity.reference_id == reference_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="设定条目不存在")
    data = payload.model_dump(exclude_unset=True)
    explicit_status = data.pop("review_status", None)
    for k, v in data.items():
        setattr(e, k, v)
    e.review_status = explicit_status or "user_edited"
    await db.commit()
    await db.refresh(e)
    return e


@router.delete("/entities/{entity_id}", status_code=204)
async def delete_entity(
    reference_id: int,
    entity_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    e = (await db.execute(select(CanonEntity).where(
        CanonEntity.id == entity_id,
        CanonEntity.reference_id == reference_id))).scalar_one_or_none()
    if e is None:
        raise HTTPException(status_code=404, detail="设定条目不存在")
    await db.delete(e)
    await db.commit()


@router.get("/stream")
async def stream_extraction(reference_id: int, ticket: str = Query(...)):
    """SSE 进度流。ticket 校验从简（与 prose 一致：前端先 POST 拿 ticket）。"""
    sub = canon_event_bus.subscribe(reference_id)

    async def gen():
        try:
            yield "data: " + json.dumps({"event": "subscribed", "reference_id": reference_id}) + "\n\n"
            while True:
                payload = await sub.queue.get()
                yield "data: " + json.dumps(payload, ensure_ascii=False) + "\n\n"
                if payload.get("event") in ("done", "failed"):
                    break
        finally:
            canon_event_bus.unsubscribe(sub)

    return StreamingResponse(gen(), media_type="text/event-stream")
```

> 注意：`from app.core.database import get_db, engine` —— 确认 `database.py` 导出了 `engine`。若名字不同（如 `async_engine`），用实际名并同步改 import。

- [ ] **Step 4: 注册路由**

Modify `backend/app/main.py`：
- 在第 40 行 `from app.routers.prose import router as prose_router` 后加：
```python
from app.routers.canon import router as canon_router
```
- 在第 147 行 `app.include_router(prose_router)` 后加：
```python
app.include_router(canon_router)
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_router.py -v`
Expected: PASS（3 passed）

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/canon.py backend/app/main.py backend/tests/test_canon_router.py
git commit -m "feat(canon): router 提取触发+任务查询+实体CRUD+SSE"
```

---

## Task 10: wizard 接入设定锚定（canon_reference_id）

**Files:**
- Modify: `backend/app/schemas/wizard.py`（给相关 Request 加 `canon_reference_id`）
- Create: `backend/app/services/canon_context.py`（构建设定锚定上下文）
- Modify: `backend/app/routers/wizard.py:90-115`（注入锚定上下文）
- Test: `backend/tests/test_canon_context.py`

> 仅做「设定锚定上下文的构建 + 注入」。锚定上下文与现有 `style_reference`（文风参考）**语义分离**：前者是"必须遵守的设定事实"，后者是"文风模仿"。

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_canon_context.py`:

```python
"""canon_context：把 reference 的 canon 实体拼成「设定锚定」prompt 块"""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.models.reference import ReferenceNovel
from app.models.canon import CanonEntity


@pytest.fixture
def session_factory(test_engine):
    return async_sessionmaker(test_engine, expire_on_commit=False)


async def test_build_canon_context_groups_and_labels(db_session, session_factory):
    ref = ReferenceNovel(title="西游记", total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    db_session.add_all([
        CanonEntity(reference_id=ref.id, entity_type="character",
                    canonical_name="乌鸡国国王", summary="被害君主", aliases=["陛下"]),
        CanonEntity(reference_id=ref.id, entity_type="worldrule",
                    canonical_name="三界体系", summary="天庭-人间-地府"),
    ])
    await db_session.commit()

    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        ctx = await build_canon_context(s, ref.id)
    assert "设定锚定" in ctx
    assert "乌鸡国国王" in ctx
    assert "陛下" in ctx          # 别名带上
    assert "三界体系" in ctx
    assert "必须遵守" in ctx       # 约束语气


async def test_build_canon_context_empty_returns_empty(db_session, session_factory):
    ref = ReferenceNovel(title="空原作", total_chars=1)
    db_session.add(ref)
    await db_session.commit()
    await db_session.refresh(ref)
    from app.services.canon_context import build_canon_context
    async with session_factory() as s:
        ctx = await build_canon_context(s, ref.id)
    assert ctx == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_context.py -v`
Expected: FAIL — `ModuleNotFoundError: app.services.canon_context`

- [ ] **Step 3: 实现 canon_context**

Create `backend/app/services/canon_context.py`:

```python
"""把原作 canon 设定拼成 wizard 的「设定锚定」prompt 块。
与 style_reference（文风参考）语义分离：这里是必须遵守的设定事实约束。
MVP：全量注入（按 importance 排序，限条目数）。后续可加 premise 关键词/向量召回。
"""
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.canon import CanonEntity

_TYPE_CN = {
    "character": "人物", "location": "地点", "ability": "能力",
    "faction": "势力", "worldrule": "世界观规则", "event": "关键事件",
}
_IMPORTANCE_RANK = {"critical": 0, "major": 1, "minor": 2}
_MAX_ENTITIES = 60


async def build_canon_context(db: AsyncSession, reference_id: int,
                              max_entities: int = _MAX_ENTITIES) -> str:
    rows = (await db.execute(select(CanonEntity).where(
        CanonEntity.reference_id == reference_id))).scalars().all()
    if not rows:
        return ""
    rows = sorted(rows, key=lambda e: _IMPORTANCE_RANK.get(e.importance, 1))[:max_entities]

    by_type: dict[str, list[CanonEntity]] = {}
    for e in rows:
        by_type.setdefault(e.entity_type, []).append(e)

    lines = [
        "【原作设定锚定——以下是二创必须遵守的原作事实，人物/能力/世界观不得与之冲突】",
    ]
    for etype, ents in by_type.items():
        lines.append(f"\n# {_TYPE_CN.get(etype, etype)}")
        for e in ents:
            alias = f"（别名：{'、'.join(e.aliases)}）" if e.aliases else ""
            summary = f"：{e.summary}" if e.summary else ""
            lines.append(f"- {e.canonical_name}{alias}{summary}")
    return "\n".join(lines)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_context.py -v`
Expected: PASS（2 passed）

- [ ] **Step 5: schema 加字段**

Modify `backend/app/schemas/wizard.py`：给含 `reference_ids: Optional[List[int]] = None` 的各 Request 类（第 106/114/149/161/174/195 行附近）逐一在该字段下方加：

```python
    canon_reference_id: Optional[int] = None  # 设定锚定原作
```

> 至少 `WizardMapsRequest`、`WizardPartsRequest`、`WizardCharactersForPartRequest`（生成主线大纲/角色的入口）必须加。其余可一并加保持一致。

- [ ] **Step 6: wizard router 注入锚定上下文**

Modify `backend/app/routers/wizard.py`：在构建 `style_reference` 的逻辑块（第 90-115 行附近）之后、调用 PROMPTS 之前，加入设定锚定拼接。示例（在已有 `style_reference = ...` 之后）：

```python
    # 设定锚定（与 style_reference 文风参考语义分离）
    canon_context = ""
    if getattr(payload, "canon_reference_id", None):
        from app.services.canon_context import build_canon_context
        canon_context = await build_canon_context(db, payload.canon_reference_id)
```

然后把 `canon_context` 拼进传给 LLM 的 prompt 输入（在该函数把 `style_reference` 拼入 prompt 的同一处，追加 `canon_context`）。具体拼接点：找到该函数内 `style_reference=style_reference or "无"` 传参处，在其 prompt 文本里前置 `canon_context`（若非空）。最小改动：

```python
    effective_premise = (canon_context + "\n\n" + payload.premise) if canon_context else payload.premise
```

并把后续用到 `payload.premise` 的地方改用 `effective_premise`。

> 实施者注意：wizard.py 有多个生成函数（maps/parts/chapters/characters）。本任务**只需改「生成主线大纲」主路径**（maps + parts，即二创"主线推演"入口）。其余函数保持不变，列入后续迭代。

- [ ] **Step 7: 加一个 wizard 集成测试**

Append to `backend/tests/test_canon_context.py`:

```python
async def test_wizard_schema_accepts_canon_reference_id():
    from app.schemas.wizard import WizardMapsRequest
    req = WizardMapsRequest(premise="穿越乌鸡国", canon_reference_id=5)
    assert req.canon_reference_id == 5
```

> 若 `WizardMapsRequest` 有其它必填字段，按其定义补齐最小构造参数。

- [ ] **Step 8: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_context.py -v`
Expected: PASS（3 passed）

- [ ] **Step 9: 提交**

```bash
git add backend/app/services/canon_context.py backend/app/schemas/wizard.py backend/app/routers/wizard.py backend/tests/test_canon_context.py
git commit -m "feat(canon): wizard 接入设定锚定（canon_reference_id）"
```

---

## Task 11: 前端 — API 客户端 + 原作设定面板

**前置事实（已勘查）：** 前端**没有**原作详情页。原作目前只在 `frontend/src/components/AiPanel.vue`（工作台侧的参考小说面板）里通过 `frontend/src/api/reference.ts`（独立函数式 API，非 `request` 默认导出）管理。canon 设定编辑 UI（分组列表/溯源展开/编辑弹窗）体量较大，塞进侧边 `AiPanel` 不合适。

**决策：** 新建一个轻量独立视图 `frontend/src/views/ReferenceCanonView.vue`，路由 `/references/:id/canon`，从 `AiPanel.vue` 的每个参考小说条目加一个「设定」入口按钮跳转进入。遵循 `feedback_no_split_layout`：单列上下堆叠 + 行展开/弹窗，**禁止左右分屏**。

**Files:**
- Create: `frontend/src/api/canon.ts`
- Create: `frontend/src/views/ReferenceCanonView.vue`
- Modify: `frontend/src/router/index.ts`（注册路由）
- Modify: `frontend/src/components/AiPanel.vue`（参考小说条目加「设定」入口按钮）
- 验证：构建通过 + 手动冒烟（前端无单测惯例，参考 ProseDetailView 仅做 build 验证）

- [ ] **Step 1: 确认路由文件与 AiPanel 中参考小说列表渲染点**

Run: `ls frontend/src/router; grep -n "references\|getReferences\|ReferenceNovel" frontend/src/components/AiPanel.vue | head`
记录：路由文件路径（通常 `frontend/src/router/index.ts`）、AiPanel 中渲染单个参考小说条目的 `v-for` 位置（用于挂「设定」按钮）。

- [ ] **Step 2: 写 API 客户端**

Create `frontend/src/api/canon.ts`（参照 `frontend/src/api/prose.ts` 的 axios 实例与写法）:

```typescript
import request from './request' // 若项目用别的 http 封装，按 prose.ts 实际 import 调整

export interface CanonEntity {
  id: number
  reference_id: number
  entity_type: string
  canonical_name: string
  aliases: string[]
  summary?: string
  attributes: Record<string, any>
  source_refs: Array<{ chapter?: string; quote?: string; offset?: number }>
  importance: string
  confidence: number
  review_status: string
}

export interface CanonJob {
  id: number
  reference_id: number
  status: string
  chunk_total: number
  chunk_done: number
  failed_chunks: number
  entity_count: number
  error?: string
}

const base = (refId: number) => `/api/v1/references/${refId}/canon`

export const canonApi = {
  startExtraction: (refId: number) => request.post(`${base(refId)}/extract`),
  getJob: (refId: number) => request.get<CanonJob>(`${base(refId)}/job`),
  listEntities: (refId: number, entityType?: string) =>
    request.get<CanonEntity[]>(`${base(refId)}/entities`,
      { params: entityType ? { entity_type: entityType } : {} }),
  createEntity: (refId: number, body: Partial<CanonEntity>) =>
    request.post<CanonEntity>(`${base(refId)}/entities`, body),
  updateEntity: (refId: number, id: number, body: Partial<CanonEntity>) =>
    request.put<CanonEntity>(`${base(refId)}/entities/${id}`, body),
  deleteEntity: (refId: number, id: number) =>
    request.delete(`${base(refId)}/entities/${id}`),
  streamUrl: (refId: number) => `${base(refId)}/stream`,
}
```

> 实施者：打开 `frontend/src/api/prose.ts` 确认真实的 http 封装名（`request`/`http`/`api`）与默认导出方式，使本文件 import 与之一致。

- [ ] **Step 3: 创建 ReferenceCanonView 视图 + 注册路由 + AiPanel 入口**

3a. Create `frontend/src/views/ReferenceCanonView.vue`，单列上下堆叠布局，从 `route.params.id` 取 `refId`，包含：
- 顶部：原作标题 + 「开始提取」按钮 → 调 `canonApi.startExtraction(refId)` → 用 `EventSource` 订阅 `canonApi.streamUrl(refId)` 显示进度条（参考 `ProseDetailView.vue` 的 SSE 订阅与关闭写法；收到 `done`/`failed` 事件后刷新列表并关闭连接）
- 主体：按 `entity_type` 分组（`el-collapse`，6 组：人物/地点/能力/势力/世界观规则/关键事件）展示 `listEntities(refId)` 结果
- 每条目：展示 `canonical_name` + 别名 + summary + `review_status` 角标（`el-tag`：ai_extracted=info，user_verified=success，user_edited=primary，user_added=warning）；可展开看 `source_refs`（章节 + quote 原文引用）
- 行内「编辑」「删除」按钮 → `updateEntity` / `deleteEntity`（删除前 `ElMessageBox.confirm`）
- 顶部「+ 新增设定」→ `el-dialog` 表单（entity_type 下拉 + canonical_name + summary）→ `createEntity`

最小可用顺序：先实现「开始提取 + 进度 + 分组列表 + 溯源展开 + 删除」，编辑/新增弹窗作为本步后续。

3b. Modify `frontend/src/router/index.ts`：在 routes 数组中加（参考现有 ProseDetail 路由的 meta/写法）：

```typescript
{
  path: '/references/:id/canon',
  name: 'reference-canon',
  component: () => import('@/views/ReferenceCanonView.vue'),
  meta: { requiresAuth: true },
},
```

3c. Modify `frontend/src/components/AiPanel.vue`：在渲染单个参考小说条目的 `v-for`（Step 1 定位）里加一个按钮：

```vue
<el-button size="small" @click="$router.push(`/references/${item.id}/canon`)">设定</el-button>
```

（`item` 用 AiPanel 中实际的循环变量名替换。）

> 遵循 `feedback_no_split_layout`：单列上下堆叠 + 行展开 + 弹窗，**禁止左右分屏**。

- [ ] **Step 4: 构建验证**

Run: `cd frontend && npm run build`
Expected: 构建成功，无 TS 类型错误。

- [ ] **Step 5: 手动冒烟（记录结果，不阻塞提交）**

启动 `docker compose up -d --build` 或本地 dev，上传一部短篇原作 → 点「开始提取」→ 观察 SSE 进度跑完 → 「设定」Tab 出现分组条目 → 展开某条看到原文 quote → 删除一条成功。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/api/canon.ts frontend/src/views/ReferenceCanonView.vue frontend/src/router/index.ts frontend/src/components/AiPanel.vue
git commit -m "feat(canon): 前端原作设定视图（提取/进度/分组/溯源/CRUD）"
```

---

## 收尾：全量回归

- [ ] **后端全量测试**

Run: `cd backend && python -m pytest tests/test_canon_models.py tests/test_canon_schemas.py tests/test_canon_event_bus.py tests/test_canon_prompts.py tests/test_canon_pipeline.py tests/test_canon_router.py tests/test_canon_context.py -v`
Expected: 全 PASS

- [ ] **冒烟确认溯源非空（准确度基线）**：end_to_end 测试已断言 `source_refs` 非空；如接真实 LLM 跑一部短篇，人工抽查 5 条设定的 quote 是否能在原文中找到。

---

## 实施顺序与依赖

```
Task1(模型) → Task2(schema) → Task3(event_bus) ┐
Task4(prompts) ─────────────────────────────────┤
                                                 ├→ Task5(CHUNK) → Task6(ATOMIC) → Task7(MERGE) → Task8(编排)
                                                 │                                                    ↓
                                                 └──────────────────────────────→ Task9(router) ────┤
                                                                                   Task10(wizard锚定) ┤
                                                                                   Task11(前端) ───────┘
```

Task1-4 可并行；Task5-8 顺序依赖（同一文件递增）；Task9 依赖 Task8；Task10 依赖 Task1；Task11 依赖 Task9。
