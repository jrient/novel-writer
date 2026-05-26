# Spec-1 知乎严选风格样本库 实施 Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一个独立的运营风格样本库：上传 txt/md/docx → 后台 embedding 索引 + LLM 抽取「风格指南片段」→ 列表/详情/检索 API + 前端页面，供 Spec-2 主工作流消费。

**Architecture:** 后端复用 `embedding_service` / `file_parser` / `ai_service`，新增 `StyleSample` + `StyleSampleChunk` 两张表（pgvector 1536 维）、`style_sample_indexer` + `style_guide_extractor` + `style_sample_pipeline` 三个服务、`style_sample` 路由（6 端点）。前端新增 `StyleSampleLibrary.vue` 页面 + API 客户端 + 路由 + 主页入口。

**Tech Stack:** Python FastAPI + SQLAlchemy 2.0 async + pgvector + Pydantic v2，pytest-asyncio + sqlite-aiosqlite 单测；Vue 3 + TypeScript + Element Plus + Pinia 前端。

参考 Spec：`docs/superpowers/specs/2026-05-26-style-sample-library-design.md`（commit `938fb9b`）

---

## 文件清单

**Backend create:**
- `backend/app/models/style_sample.py`
- `backend/app/schemas/style_sample.py`
- `backend/app/services/style_sample_indexer.py`
- `backend/app/services/style_guide_extractor.py`
- `backend/app/services/style_sample_pipeline.py`
- `backend/app/routers/style_sample.py`
- `backend/tests/test_style_sample_models.py`
- `backend/tests/test_style_sample_indexer.py`
- `backend/tests/test_style_guide_extractor.py`
- `backend/tests/test_style_sample_router.py`

**Backend modify:**
- `backend/app/models/__init__.py:1` — register `StyleSample`, `StyleSampleChunk`
- `backend/app/routers/__init__.py:1` — register `style_sample_router`
- `backend/app/main.py:36` — import + include router

**Frontend create:**
- `frontend/src/api/styleSample.ts`
- `frontend/src/views/StyleSampleLibrary.vue`

**Frontend modify:**
- `frontend/src/router/index.ts:101` — add route entry
- `frontend/src/views/ProjectListView.vue:19` — add nav chip

---

## Task 1：StyleSample / StyleSampleChunk ORM 模型

**Files:**
- Create: `backend/app/models/style_sample.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_style_sample_models.py`

- [ ] **Step 1: 写失败的模型测试**

写文件 `backend/tests/test_style_sample_models.py`：

```python
"""StyleSample / StyleSampleChunk 模型 schema 与 CASCADE 验证"""
import pytest
from sqlalchemy import select

from app.models.style_sample import StyleSample, StyleSampleChunk


@pytest.mark.asyncio
async def test_create_style_sample_minimal(db_session):
    s = StyleSample(title="测试样本", content="正文 1234")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    assert s.id is not None
    assert s.title == "测试样本"
    assert s.index_status == "pending"  # 默认值
    assert s.total_chars == 0           # 默认值


@pytest.mark.asyncio
async def test_create_style_sample_full(db_session):
    s = StyleSample(
        title="完整字段",
        author="作者甲",
        source="知乎严选",
        genre="都市言情",
        tags='["甜文", "高糖"]',
        notes="运营备注",
        file_path="uploads/style/x.txt",
        file_format="txt",
        content="原文" * 100,
        total_chars=200,
        style_guide='{"structured": {}, "prose_excerpt": "", "prompt_fragment": ""}',
        extraction_model="claude-sonnet-4",
        index_status="ready",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    assert s.genre == "都市言情"
    assert s.index_status == "ready"


@pytest.mark.asyncio
async def test_chunk_cascade_delete(db_session):
    s = StyleSample(title="将被删", content="x")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    c = StyleSampleChunk(
        sample_id=s.id, chunk_index=0, content="片段一", char_count=3
    )
    db_session.add(c)
    await db_session.commit()

    # 删 sample 应级联删 chunk
    await db_session.delete(s)
    await db_session.commit()

    remaining = (await db_session.execute(select(StyleSampleChunk))).scalars().all()
    assert remaining == []
```

- [ ] **Step 2: 跑测试，确认 ImportError**

```bash
cd backend && pytest tests/test_style_sample_models.py -v
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.models.style_sample'`

- [ ] **Step 3: 写模型实现**

写文件 `backend/app/models/style_sample.py`：

```python
"""知乎严选风格样本 ORM 模型

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第三节。
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, DateTime, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class StyleSample(Base):
    """风格样本（全局共享，运营资产，无 owner_id）"""
    __tablename__ = "style_samples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_format: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    total_chars: Mapped[int] = mapped_column(Integer, default=0)

    style_guide: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    index_status: Mapped[str] = mapped_column(String(20), default="pending")
    index_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class StyleSampleChunk(Base):
    """样本片段向量"""
    __tablename__ = "style_sample_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sample_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("style_samples.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

- [ ] **Step 4: 注册新模型到 `models/__init__.py`**

修改 `backend/app/models/__init__.py`，在 `KnowledgeEntry` 行后加入：

```python
from app.models.knowledge import KnowledgeEntry
from app.models.style_sample import StyleSample, StyleSampleChunk  # ← 新增
```

并在 `__all__` 列表中加入 `"StyleSample", "StyleSampleChunk"`。

- [ ] **Step 5: 跑测试，确认通过**

```bash
cd backend && pytest tests/test_style_sample_models.py -v
```

预期：3 条全 PASS。

> **SQLite 注意**：测试用 SQLite 不支持 `pgvector.Vector` 实际索引行为；但 column 定义在 SQLite 下退化为 TEXT 仍可建表。模型测试本身不访问 embedding 字段所以不受影响。

- [ ] **Step 6: 提交**

```bash
git add backend/app/models/style_sample.py backend/app/models/__init__.py backend/tests/test_style_sample_models.py
git commit -m "feat(style-sample): StyleSample / StyleSampleChunk ORM 模型

Constraint: 复用 pgvector(1536) 与现有 NovelChunk 维度一致
Confidence: high
Scope-risk: narrow"
```

---

## Task 2：Pydantic schemas

**Files:**
- Create: `backend/app/schemas/style_sample.py`

无独立测试——schemas 会在 router 测试里间接覆盖。

- [ ] **Step 1: 写 schemas**

写文件 `backend/app/schemas/style_sample.py`：

```python
"""StyleSample API schemas

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第四节。
"""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class StyleGuideStructured(BaseModel):
    pov: Optional[str] = None
    tense: Optional[str] = None
    sentence_length: Optional[str] = None
    dialogue_density: Optional[str] = None
    pacing: Optional[str] = None
    opening_formula: Optional[str] = None
    ending_formula: Optional[str] = None
    signature_devices: list[str] = Field(default_factory=list)


class StyleGuide(BaseModel):
    structured: StyleGuideStructured = Field(default_factory=StyleGuideStructured)
    prose_excerpt: str = ""
    prompt_fragment: str = ""


class StyleSampleSummary(BaseModel):
    """列表项 —— 不含 content / chunks"""
    id: int
    title: str
    author: Optional[str]
    source: Optional[str]
    genre: Optional[str]
    tags: Optional[str]
    total_chars: int
    index_status: str
    index_error: Optional[str]
    extracted_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class StyleSampleDetail(StyleSampleSummary):
    """详情 —— 含 content / 解析后的 style_guide / file 元信息"""
    file_path: Optional[str]
    file_format: Optional[str]
    notes: Optional[str]
    content: str
    style_guide: Optional[StyleGuide] = None  # JSON 字段已解析
    extraction_model: Optional[str]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    filter: dict[str, Any] = Field(default_factory=dict)  # {"genre": "...", "tags": [...]}


class SearchHitChunk(BaseModel):
    chunk_index: int
    content: str
    char_count: int
    similarity: float


class SearchHit(BaseModel):
    sample: StyleSampleSummary
    top_chunks: list[SearchHitChunk]
    style_guide: Optional[StyleGuide] = None
```

- [ ] **Step 2: 冒烟检查 import**

```bash
cd backend && python -c "from app.schemas.style_sample import StyleSampleDetail, SearchRequest; print('ok')"
```

预期：输出 `ok`，无异常。

- [ ] **Step 3: 提交**

```bash
git add backend/app/schemas/style_sample.py
git commit -m "feat(style-sample): Pydantic schemas (Summary/Detail/Search)

Confidence: high
Scope-risk: narrow"
```

---

## Task 3：chunk 切分器（纯函数）

**Files:**
- Create: `backend/app/services/style_sample_indexer.py`（先写 `split_chunks` 一部分）
- Test: `backend/tests/test_style_sample_indexer.py`

- [ ] **Step 1: 写失败的切分测试**

写文件 `backend/tests/test_style_sample_indexer.py`：

```python
"""StyleSample chunk 切分 + 索引服务测试"""
import pytest

from app.services.style_sample_indexer import split_chunks


def test_split_chunks_short_text_single():
    """短文本只产 1 个 chunk，即使少于 100 字也保留"""
    text = "短短的一段。"
    chunks = split_chunks(text)
    assert len(chunks) == 1
    assert chunks[0] == "短短的一段。"


def test_split_chunks_by_paragraph():
    """段落已经在 100-500 字内，按段切，不合并不切分"""
    p1 = "第一段。" * 50   # 200 字
    p2 = "第二段。" * 60   # 240 字
    text = f"{p1}\n\n{p2}"
    chunks = split_chunks(text)
    assert len(chunks) == 2
    assert chunks[0] == p1
    assert chunks[1] == p2


def test_split_chunks_merge_short_with_next():
    """少于 100 字的段并入下一段"""
    short = "短段。" * 10                # 30 字
    next_p = "下一段。" * 50              # 200 字
    text = f"{short}\n\n{next_p}"
    chunks = split_chunks(text)
    assert len(chunks) == 1
    assert chunks[0].startswith(short)
    assert chunks[0].endswith(next_p)


def test_split_chunks_hard_split_long_at_sentence_end():
    """超 500 字的段在 500 字往前找句末符切；找不到才硬切"""
    text = "一" * 480 + "。" + "二" * 200 + "。"
    chunks = split_chunks(text)
    # 应在 480 处的句号切：第一段 ≤500 字、第二段剩余
    assert len(chunks) == 2
    assert chunks[0].endswith("。")
    assert len(chunks[0]) <= 500
    assert chunks[1].startswith("二")


def test_split_chunks_hard_split_no_sentence_mark():
    """500 字内无句末符 → 硬切到 500"""
    text = "甲" * 700  # 全角无标点
    chunks = split_chunks(text)
    assert len(chunks) == 2
    assert len(chunks[0]) == 500
    assert len(chunks[1]) == 200


def test_split_chunks_trailing_short_orphan():
    """最后一段少于 100 字且没有下一段可合 —— 允许独立"""
    p1 = "主段。" * 60
    short = "尾。"
    text = f"{p1}\n\n{short}"
    chunks = split_chunks(text)
    assert short in chunks
```

- [ ] **Step 2: 跑测试，确认 ImportError**

```bash
cd backend && pytest tests/test_style_sample_indexer.py -v
```

预期：FAIL，`ModuleNotFoundError: No module named 'app.services.style_sample_indexer'`

- [ ] **Step 3: 写 `split_chunks` 实现**

新建 `backend/app/services/style_sample_indexer.py`：

```python
"""StyleSample 索引服务：chunk 切分 + embedding 写入

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第六节。
"""
from typing import List

CHUNK_MIN = 100
CHUNK_MAX = 500
SENTENCE_END_MARKS = "。！？…"


def _hard_split_long_paragraph(text: str) -> List[str]:
    """超 CHUNK_MAX 的段落硬切：先找 CHUNK_MAX 内最后的句末符，没有就切到 CHUNK_MAX。"""
    out: List[str] = []
    remaining = text
    while len(remaining) > CHUNK_MAX:
        window = remaining[:CHUNK_MAX]
        # 从 CHUNK_MAX 倒着找句末符；保留至少 (CHUNK_MAX - 100) = 400 字
        cut = -1
        for i in range(CHUNK_MAX - 1, CHUNK_MAX - 101, -1):
            if i < 0:
                break
            if window[i] in SENTENCE_END_MARKS:
                cut = i + 1
                break
        if cut == -1:
            cut = CHUNK_MAX
        out.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        out.append(remaining)
    return out


def split_chunks(content: str) -> List[str]:
    """按段落切分，少 100 字段并入下一段，超 500 字按句末符硬切。

    规则详见 spec 第六节。
    """
    # 先按双换行切段，去空白
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    # 再按单换行二次切（覆盖未规范化的输入）
    refined: List[str] = []
    for p in paragraphs:
        refined.extend(s.strip() for s in p.split("\n") if s.strip())

    if not refined:
        return []

    # 合并短段：少于 CHUNK_MIN 的并入下一段；尾段单独保留
    merged: List[str] = []
    buffer = ""
    for p in refined:
        if buffer:
            buffer = buffer + p
            if len(buffer) >= CHUNK_MIN:
                merged.append(buffer)
                buffer = ""
        elif len(p) < CHUNK_MIN:
            buffer = p
        else:
            merged.append(p)
    if buffer:
        merged.append(buffer)  # 尾部 orphan 短段独立

    # 对超长段落硬切
    out: List[str] = []
    for p in merged:
        if len(p) > CHUNK_MAX:
            out.extend(_hard_split_long_paragraph(p))
        else:
            out.append(p)
    return out
```

- [ ] **Step 4: 跑测试，确认通过**

```bash
cd backend && pytest tests/test_style_sample_indexer.py -v
```

预期：6 条全 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/style_sample_indexer.py backend/tests/test_style_sample_indexer.py
git commit -m "feat(style-sample): split_chunks 切分纯函数(段落+合并短段+句末硬切)

Constraint: 中文标点(。！？…)优先,硬切回退到 500 字
Confidence: high
Scope-risk: narrow"
```

---

## Task 4：indexer 端到端（embedding + DB 写入）

**Files:**
- Modify: `backend/app/services/style_sample_indexer.py`（追加 `index_sample`）
- Test: `backend/tests/test_style_sample_indexer.py`（追加）

- [ ] **Step 1: 追加失败的端到端测试**

在 `backend/tests/test_style_sample_indexer.py` 末尾追加：

```python
import pytest

from app.models.style_sample import StyleSample, StyleSampleChunk
from sqlalchemy import select


@pytest.mark.asyncio
async def test_index_sample_writes_chunks_with_embeddings(db_session, monkeypatch):
    """索引一个样本：切 chunk → 调（mock）embedding → 写 DB"""
    from app.services import style_sample_indexer

    # mock embedding：批量调用接收 N 条文本，返回 N 个 1536 维零向量
    async def fake_embed(texts):
        return [[0.0] * 1536 for _ in texts]

    monkeypatch.setattr(
        "app.services.style_sample_indexer.embedding_service.generate_embeddings",
        fake_embed,
    )

    # 准备一个样本（已含 content；总 600 字 → 应切 2 chunks）
    s = StyleSample(title="t", content=("段一。" * 60) + "\n\n" + ("段二。" * 70))
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    await style_sample_indexer.index_sample(db_session, s.id)

    # 读 chunks
    rows = (await db_session.execute(
        select(StyleSampleChunk).where(StyleSampleChunk.sample_id == s.id).order_by(StyleSampleChunk.chunk_index)
    )).scalars().all()
    assert len(rows) >= 2
    assert all(r.embedding is not None for r in rows)
    assert all(r.char_count == len(r.content) for r in rows)
    assert [r.chunk_index for r in rows] == list(range(len(rows)))


@pytest.mark.asyncio
async def test_index_sample_failure_marks_failed_and_no_partial(db_session, monkeypatch):
    """embedding 异常时,sample 不写 chunk,留 sample 行(由 pipeline 标 failed)"""
    from app.services import style_sample_indexer

    async def boom(texts):
        raise RuntimeError("embed down")

    monkeypatch.setattr(
        "app.services.style_sample_indexer.embedding_service.generate_embeddings",
        boom,
    )

    s = StyleSample(title="t2", content="一段。" * 60)
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    with pytest.raises(RuntimeError, match="embed down"):
        await style_sample_indexer.index_sample(db_session, s.id)

    # 应无 chunk
    rows = (await db_session.execute(
        select(StyleSampleChunk).where(StyleSampleChunk.sample_id == s.id)
    )).scalars().all()
    assert rows == []
```

- [ ] **Step 2: 跑测试，确认 AttributeError**

```bash
cd backend && pytest tests/test_style_sample_indexer.py::test_index_sample_writes_chunks_with_embeddings -v
```

预期：FAIL，`AttributeError: module 'app.services.style_sample_indexer' has no attribute 'index_sample'`

- [ ] **Step 3: 追加 `index_sample` 实现**

在 `backend/app/services/style_sample_indexer.py` 末尾追加：

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.services.embedding import embedding_service
from app.models.style_sample import StyleSample, StyleSampleChunk


EMBED_BATCH_SIZE = 50


async def index_sample(session: AsyncSession, sample_id: int) -> int:
    """对指定 sample 切 chunk + 生 embedding + 写表。返回写入 chunk 数。

    失败处理：embedding 抛出 → 上抛给调用方；本函数保证不留半成品 chunk
    （生 embedding 失败前不写任何 chunk 行）。
    """
    sample = (await session.execute(
        select(StyleSample).where(StyleSample.id == sample_id)
    )).scalar_one()

    # 先清掉旧 chunk（reindex 路径）
    await session.execute(
        delete(StyleSampleChunk).where(StyleSampleChunk.sample_id == sample_id)
    )

    chunks = split_chunks(sample.content)
    if not chunks:
        await session.commit()
        return 0

    # 分批生 embedding
    embeddings: List[list] = []
    for i in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[i : i + EMBED_BATCH_SIZE]
        vecs = await embedding_service.generate_embeddings(batch)
        embeddings.extend(vecs)

    # 全成功后才写
    for idx, (text, vec) in enumerate(zip(chunks, embeddings)):
        session.add(StyleSampleChunk(
            sample_id=sample_id,
            chunk_index=idx,
            content=text,
            char_count=len(text),
            embedding=vec,
        ))
    await session.commit()
    return len(chunks)
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && pytest tests/test_style_sample_indexer.py -v
```

预期：全部 8 条 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/style_sample_indexer.py backend/tests/test_style_sample_indexer.py
git commit -m "feat(style-sample): index_sample 端到端 (切 chunk + embedding + 写表)

Constraint: 全 batch 成功后才写 chunks,不留半成品
Confidence: high
Scope-risk: narrow"
```

---

## Task 5：style_guide_extractor 服务

**Files:**
- Create: `backend/app/services/style_guide_extractor.py`
- Test: `backend/tests/test_style_guide_extractor.py`

- [ ] **Step 1: 写失败的抽取测试**

写文件 `backend/tests/test_style_guide_extractor.py`：

```python
"""style_guide_extractor 抽取服务测试 —— 全部 mock LLM"""
import json
import pytest

from app.services import style_guide_extractor


VALID_LLM_OUTPUT = json.dumps({
    "structured": {
        "pov": "第一人称",
        "tense": "过去时",
        "sentence_length": "短句为主",
        "dialogue_density": "high",
        "pacing": "强反转密集",
        "opening_formula": "倒叙抛悬念",
        "ending_formula": "高甜余韵",
        "signature_devices": ["内心独白", "短段落分隔"],
    },
    "prose_excerpt": "一段示范原文文本，约一百多字。" * 5,
    "prompt_fragment": "用第一人称过去时，短句为主……约三百字。" * 3,
}, ensure_ascii=False)


@pytest.mark.asyncio
async def test_extract_returns_parsed_guide(monkeypatch):
    async def fake_gen(prompt, provider=None, max_tokens=None):
        return VALID_LLM_OUTPUT

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    guide_json, model = await style_guide_extractor.extract("《标题》", "正文" * 100)
    parsed = json.loads(guide_json)
    assert parsed["structured"]["pov"] == "第一人称"
    assert len(parsed["prose_excerpt"]) >= 100
    assert isinstance(model, str) and model  # 返回用的 model 名


@pytest.mark.asyncio
async def test_extract_raises_on_invalid_json(monkeypatch):
    async def fake_gen(prompt, provider=None, max_tokens=None):
        return "这不是 json 也不是 markdown"

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    with pytest.raises(style_guide_extractor.StyleGuideExtractionError):
        await style_guide_extractor.extract("t", "c")


@pytest.mark.asyncio
async def test_extract_strips_markdown_code_fence(monkeypatch):
    """允许 LLM 套了 ```json 围栏，应能剥掉再解析"""
    fenced = f"```json\n{VALID_LLM_OUTPUT}\n```"

    async def fake_gen(prompt, provider=None, max_tokens=None):
        return fenced

    monkeypatch.setattr(
        "app.services.style_guide_extractor.AIService.generate_text", fake_gen
    )

    guide_json, _ = await style_guide_extractor.extract("t", "c")
    parsed = json.loads(guide_json)
    assert parsed["structured"]["pov"] == "第一人称"
```

- [ ] **Step 2: 跑测试，确认 ImportError**

```bash
cd backend && pytest tests/test_style_guide_extractor.py -v
```

预期：FAIL，`ModuleNotFoundError`

- [ ] **Step 3: 写 extractor 实现**

写文件 `backend/app/services/style_guide_extractor.py`：

```python
"""风格指南片段抽取服务

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第五节。
"""
import json
import re
from typing import Tuple

from app.core.config import settings
from app.services.ai_service import AIService


class StyleGuideExtractionError(Exception):
    """LLM 返回无法解析为 JSON，或缺关键字段"""


PROMPT_TEMPLATE = """你是一位资深风格分析师，专门分析中文短篇网文的写作风格。
分析下面给定的短篇全文，严格输出 JSON，三段：

1. structured: 客观可枚举的风格维度（pov / tense / sentence_length /
   dialogue_density / pacing / opening_formula / ending_formula /
   signature_devices[]）。每项给一个简短中文标签或 1-2 句话描述。

2. prose_excerpt: 从原文中挑选一段最能体现该作整体调性的连续段落
   （不少于 100 字、不超过 250 字）。原文照抄，不要改写。

3. prompt_fragment: 一段约 300 字的"风格指南"，必须可以直接拼接到
   下游小说生成 prompt 的 system 段里。要描述：人称/时态/句长偏好/
   段落分隔风格/对白节奏/情绪表达手法/开场和结尾的常用套路。
   不要包含原文具体人名、地名、情节。只描述"怎么写"，不描述"写什么"。

严格 JSON 输出，不要 markdown 代码块。

《{title}》全文：
{content}
"""


_CODE_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)


def _strip_code_fence(s: str) -> str:
    """剥掉 LLM 偶尔套上的 ```json ... ``` 围栏"""
    return _CODE_FENCE_RE.sub("", s).strip()


def _resolve_model_name() -> str:
    """记录抽取实际用到的 model（按 settings 默认 provider 选）"""
    # 与 ai_service._get_available_provider 同样的优先级
    if settings.OPENAI_API_KEY:
        return f"openai/{settings.OPENAI_MODEL}"
    if settings.ANTHROPIC_API_KEY:
        return f"anthropic/{settings.ANTHROPIC_MODEL}"
    if settings.OLLAMA_BASE_URL:
        return f"ollama/{settings.OLLAMA_MODEL}"
    return "demo"


async def extract(title: str, content: str) -> Tuple[str, str]:
    """跑 LLM 抽取，返回 (style_guide_json_str, extraction_model)。

    成功 → JSON 字符串可直接写入 StyleSample.style_guide
    失败 → 抛 StyleGuideExtractionError
    """
    prompt = PROMPT_TEMPLATE.format(title=title, content=content)
    raw = await AIService.generate_text(prompt, max_tokens=2000)
    cleaned = _strip_code_fence(raw)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise StyleGuideExtractionError(
            f"LLM 输出无法解析为 JSON: {e.msg}; 头 200 字: {cleaned[:200]}"
        ) from e

    if not isinstance(parsed, dict) or "structured" not in parsed or "prompt_fragment" not in parsed:
        raise StyleGuideExtractionError(
            f"JSON 缺关键字段; keys={list(parsed) if isinstance(parsed, dict) else type(parsed).__name__}"
        )

    return json.dumps(parsed, ensure_ascii=False), _resolve_model_name()
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && pytest tests/test_style_guide_extractor.py -v
```

预期：3 条全 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/style_guide_extractor.py backend/tests/test_style_guide_extractor.py
git commit -m "feat(style-sample): style_guide_extractor (LLM JSON 抽取 + 围栏剥离)

Constraint: prompt_fragment 必须剥离原文情节(写在 prompt 内文)
Rejected: 引入 instructor/pydantic-ai 做 JSON 校验 | 性价比低
Confidence: medium
Scope-risk: narrow
Not-tested: 真实 LLM 抽出 prompt_fragment 是否真"只描述怎么写"——手工验收阶段把关"
```

---

## Task 6：pipeline 编排器（indexer + extractor + 状态管理）

**Files:**
- Create: `backend/app/services/style_sample_pipeline.py`
- Test: `backend/tests/test_style_sample_router.py`（pipeline 行为留到 router 测试里间接覆盖）

无独立单测——router 测试已涵盖 indexing → ready 状态切换。

- [ ] **Step 1: 写 pipeline 编排**

写文件 `backend/app/services/style_sample_pipeline.py`：

```python
"""StyleSample 后台索引 + 抽取 pipeline 编排

包装 indexer + extractor，负责：
  - 把 index_status 推进到 indexing / ready / failed
  - 写 index_error
  - 写 extracted_at / extraction_model
  - 任何一步失败 → 整体 failed，chunks 全删（indexer 内自己处理）
"""
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncEngine

from app.models.style_sample import StyleSample
from app.services import style_sample_indexer, style_guide_extractor

logger = logging.getLogger(__name__)


async def run(session_factory: async_sessionmaker, sample_id: int) -> None:
    """对 sample 跑完整 pipeline：embedding + 抽取 → 落库。

    每个阶段开自己的 session（background task 路径，外层 HTTP session 已关）。
    任何阶段失败 → 标 failed + 写 error，并保证不留半成品。
    """
    # 阶段 1：标 indexing
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.index_status = "indexing"
        sample.index_error = None
        await session.commit()
        title = sample.title
        content = sample.content

    # 阶段 2：embedding
    try:
        async with session_factory() as session:
            await style_sample_indexer.index_sample(session, sample_id)
    except Exception as e:
        logger.exception("style_sample embedding 失败 sample_id=%s", sample_id)
        await _mark_failed(session_factory, sample_id, f"embedding 失败: {e}")
        return

    # 阶段 3：LLM 抽取
    try:
        guide_json, model_name = await style_guide_extractor.extract(title, content)
    except style_guide_extractor.StyleGuideExtractionError as e:
        logger.exception("style_sample 抽取失败 sample_id=%s", sample_id)
        # 抽取失败：清掉刚写的 chunks（保持 "全失败/全成功"）
        async with session_factory() as session:
            await style_sample_indexer._delete_chunks_only(session, sample_id)
        await _mark_failed(session_factory, sample_id, f"抽取失败: {e}")
        return

    # 阶段 4：写抽取结果 + 标 ready
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.style_guide = guide_json
        sample.extraction_model = model_name
        sample.extracted_at = datetime.utcnow()
        sample.index_status = "ready"
        sample.index_error = None
        await session.commit()


async def _mark_failed(session_factory: async_sessionmaker, sample_id: int, error: str) -> None:
    async with session_factory() as session:
        sample = (await session.execute(
            select(StyleSample).where(StyleSample.id == sample_id)
        )).scalar_one()
        sample.index_status = "failed"
        sample.index_error = error[:2000]  # Text 列限尺寸
        await session.commit()
```

- [ ] **Step 2: 在 indexer 中加上 `_delete_chunks_only` helper**

在 `backend/app/services/style_sample_indexer.py` 末尾追加：

```python
async def _delete_chunks_only(session: AsyncSession, sample_id: int) -> None:
    """供 pipeline 在抽取失败回退时清空 chunks（不动 sample 行）"""
    await session.execute(
        delete(StyleSampleChunk).where(StyleSampleChunk.sample_id == sample_id)
    )
    await session.commit()
```

- [ ] **Step 3: 冒烟 import 检查**

```bash
cd backend && python -c "from app.services.style_sample_pipeline import run; print('ok')"
```

预期：输出 `ok`。

- [ ] **Step 4: 提交**

```bash
git add backend/app/services/style_sample_pipeline.py backend/app/services/style_sample_indexer.py
git commit -m "feat(style-sample): pipeline 编排器(indexing→ready 状态机)

Constraint: 任一阶段失败 → 整体 failed,无半成品 chunks
Rejected: 阶段化 retry | MVP 简单优先,用户可手动 reindex
Confidence: high
Scope-risk: narrow"
```

---

## Task 7：router scaffold + POST 上传

**Files:**
- Create: `backend/app/routers/style_sample.py`
- Test: `backend/tests/test_style_sample_router.py`

- [ ] **Step 1: 写失败的上传测试**

写文件 `backend/tests/test_style_sample_router.py`：

```python
"""style_sample router 测试 —— 全程 mock pipeline 与 ai/embedding"""
import io
import json
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
    # pipeline 应被 schedule（FastAPI BackgroundTasks 在 TestClient 同步跑）
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
    assert resp.status_code == 422  # FastAPI Form 必填
```

- [ ] **Step 2: 跑测试，确认 404**

```bash
cd backend && pytest tests/test_style_sample_router.py -v
```

预期：FAIL，404 Not Found（router 未注册）

- [ ] **Step 3: 写 router**

写文件 `backend/app/routers/style_sample.py`：

```python
"""风格样本库 API

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第四节。
"""
import json
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.models.style_sample import StyleSample
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.style_sample import StyleGuide, StyleSampleSummary
from app.services import style_sample_pipeline
from app.services.file_parser import FileParser

router = APIRouter(prefix="/api/v1/style-samples", tags=["style-samples"])

UPLOAD_DIR = "uploads/style_samples"
ALLOWED_FORMATS = {"txt", "md", "markdown", "docx"}


def _parse_upload(file: UploadFile, raw: bytes) -> str:
    fmt = (os.path.splitext(file.filename or "")[1] or "").lstrip(".").lower()
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(400, f"不支持的文件格式 .{fmt}（仅 txt/md/docx）")
    parser = FileParser()
    try:
        if fmt == "docx":
            result = parser.parse_docx(raw)
        elif fmt in ("md", "markdown"):
            result = parser.parse_markdown(raw)
        else:
            result = parser.parse_txt(raw)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败: {e}")
    return result.content if hasattr(result, "content") else str(result)


def _to_summary(s: StyleSample) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "author": s.author,
        "source": s.source,
        "genre": s.genre,
        "tags": s.tags,
        "total_chars": s.total_chars,
        "index_status": s.index_status,
        "index_error": s.index_error,
        "extracted_at": s.extracted_at.isoformat() if s.extracted_at else None,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.post("", response_model=StyleSampleSummary)
async def upload_sample(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(default=None),
    source: Optional[str] = Form(default=None),
    genre: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    content = _parse_upload(file, raw)

    # 落盘 + 入库（pending）
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fmt = (os.path.splitext(file.filename or "")[1] or ".txt").lstrip(".").lower()
    fname = f"{uuid.uuid4().hex}.{fmt}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(raw)

    sample = StyleSample(
        title=title,
        author=author,
        source=source,
        genre=genre,
        tags=tags,
        notes=notes,
        file_path=fpath,
        file_format=fmt,
        content=content,
        total_chars=len(content),
        index_status="pending",
    )
    db.add(sample)
    await db.commit()
    await db.refresh(sample)

    background.add_task(style_sample_pipeline.run, async_session, sample.id)
    return _to_summary(sample)
```

- [ ] **Step 4: 注册 router 进 `routers/__init__.py` 和 `main.py`**

修改 `backend/app/routers/__init__.py`，append：

```python
from app.routers.style_sample import router as style_sample_router
```

并在 `__all__` 加 `"style_sample_router"`。

修改 `backend/app/main.py:36`，把 `adaptation_router,` 后加一行：

```python
    adaptation_router,
    style_sample_router,   # ← 新增
```

并在 `app.include_router(adaptation_router)` 后追加：

```python
app.include_router(style_sample_router)
```

- [ ] **Step 5: 跑上传测试**

```bash
cd backend && pytest tests/test_style_sample_router.py::test_upload_creates_sample_pending tests/test_style_sample_router.py::test_upload_rejects_unsupported_format tests/test_style_sample_router.py::test_upload_requires_title -v
```

预期：3 条全 PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/app/routers/style_sample.py backend/app/routers/__init__.py backend/app/main.py backend/tests/test_style_sample_router.py
git commit -m "feat(style-sample): router scaffold + POST 上传(同步建行+后台索引)

Constraint: BackgroundTasks 异步跑 pipeline,HTTP 立即返回 pending
Confidence: high
Scope-risk: narrow"
```

---

## Task 8：GET 列表 + GET 详情

**Files:**
- Modify: `backend/app/routers/style_sample.py`
- Test: `backend/tests/test_style_sample_router.py`

- [ ] **Step 1: 追加测试**

在 `backend/tests/test_style_sample_router.py` 末尾追加：

```python
from app.models.style_sample import StyleSample


@pytest.mark.asyncio
async def test_list_returns_summaries_filterable(client, db_session):
    db_session.add_all([
        StyleSample(title="A 都市", genre="都市言情", content="x"),
        StyleSample(title="B 悬疑", genre="悬疑", content="y"),
    ])
    await db_session.commit()

    resp = client.get("/api/v1/style-samples")
    assert resp.status_code == 200
    items = resp.json()
    assert {it["title"] for it in items} == {"A 都市", "B 悬疑"}
    # 列表不应含 content
    assert "content" not in items[0]

    resp = client.get("/api/v1/style-samples?genre=都市言情")
    assert [it["title"] for it in resp.json()] == ["A 都市"]


@pytest.mark.asyncio
async def test_detail_returns_content_and_parsed_guide(client, db_session):
    guide = json.dumps({
        "structured": {"pov": "第一人称", "signature_devices": []},
        "prose_excerpt": "节选...",
        "prompt_fragment": "片段...",
    }, ensure_ascii=False)
    s = StyleSample(
        title="详情用",
        content="原文全文 1234",
        style_guide=guide,
        extraction_model="test-model",
        index_status="ready",
    )
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    resp = client.get(f"/api/v1/style-samples/{s.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "原文全文 1234"
    assert body["style_guide"]["structured"]["pov"] == "第一人称"
    assert body["style_guide"]["prompt_fragment"] == "片段..."


@pytest.mark.asyncio
async def test_detail_404(client):
    resp = client.get("/api/v1/style-samples/9999")
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试，确认 404**

```bash
cd backend && pytest tests/test_style_sample_router.py::test_list_returns_summaries_filterable tests/test_style_sample_router.py::test_detail_returns_content_and_parsed_guide tests/test_style_sample_router.py::test_detail_404 -v
```

预期：FAIL（404，端点未实现）

- [ ] **Step 3: 实现端点**

在 `backend/app/routers/style_sample.py` 末尾追加：

```python
from sqlalchemy import select

from app.schemas.style_sample import StyleSampleDetail


@router.get("", response_model=list[StyleSampleSummary])
async def list_samples(
    genre: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(StyleSample).order_by(StyleSample.created_at.desc())
    if genre:
        stmt = stmt.where(StyleSample.genre == genre)
    rows = (await db.execute(stmt)).scalars().all()
    return [_to_summary(s) for s in rows]


@router.get("/{sample_id}", response_model=StyleSampleDetail)
async def get_sample(
    sample_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = (await db.execute(
        select(StyleSample).where(StyleSample.id == sample_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "样本不存在")
    body = _to_summary(s)
    body.update({
        "file_path": s.file_path,
        "file_format": s.file_format,
        "notes": s.notes,
        "content": s.content,
        "extraction_model": s.extraction_model,
        "style_guide": json.loads(s.style_guide) if s.style_guide else None,
    })
    return body
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && pytest tests/test_style_sample_router.py -v
```

预期：全部测试 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/style_sample.py backend/tests/test_style_sample_router.py
git commit -m "feat(style-sample): GET 列表(支持 genre filter) + GET 详情(解析 style_guide)"
```

---

## Task 9：DELETE + POST /{id}/reindex

**Files:**
- Modify: `backend/app/routers/style_sample.py`
- Test: `backend/tests/test_style_sample_router.py`

- [ ] **Step 1: 追加测试**

在测试文件末尾追加：

```python
@pytest.mark.asyncio
async def test_delete_cascades_chunks(client, db_session):
    from app.models.style_sample import StyleSampleChunk
    from sqlalchemy import select as _sel

    s = StyleSample(title="del", content="x")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)
    db_session.add(StyleSampleChunk(sample_id=s.id, chunk_index=0, content="片", char_count=1))
    await db_session.commit()

    resp = client.delete(f"/api/v1/style-samples/{s.id}")
    assert resp.status_code == 204

    remaining = (await db_session.execute(_sel(StyleSampleChunk))).scalars().all()
    assert remaining == []


@pytest.mark.asyncio
async def test_reindex_resets_status_and_runs_pipeline(client, db_session):
    s = StyleSample(title="re", content="x", index_status="failed", index_error="boom")
    db_session.add(s)
    await db_session.commit()
    await db_session.refresh(s)

    with patch("app.routers.style_sample.style_sample_pipeline.run", new=AsyncMock()) as mock_run:
        resp = client.post(f"/api/v1/style-samples/{s.id}/reindex")
    assert resp.status_code == 200
    assert resp.json()["index_status"] == "pending"
    mock_run.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_404(client):
    resp = client.delete("/api/v1/style-samples/9999")
    assert resp.status_code == 404
```

- [ ] **Step 2: 跑测试，确认 fail**

```bash
cd backend && pytest tests/test_style_sample_router.py::test_delete_cascades_chunks tests/test_style_sample_router.py::test_reindex_resets_status_and_runs_pipeline tests/test_style_sample_router.py::test_delete_404 -v
```

预期：FAIL（404）

- [ ] **Step 3: 实现端点**

在 `backend/app/routers/style_sample.py` 末尾追加：

```python
from fastapi import Response


@router.delete("/{sample_id}", status_code=204)
async def delete_sample(
    sample_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = (await db.execute(
        select(StyleSample).where(StyleSample.id == sample_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "样本不存在")
    await db.delete(s)
    await db.commit()
    return Response(status_code=204)


@router.post("/{sample_id}/reindex", response_model=StyleSampleSummary)
async def reindex_sample(
    sample_id: int,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = (await db.execute(
        select(StyleSample).where(StyleSample.id == sample_id)
    )).scalar_one_or_none()
    if not s:
        raise HTTPException(404, "样本不存在")
    s.index_status = "pending"
    s.index_error = None
    s.style_guide = None
    s.extracted_at = None
    s.extraction_model = None
    await db.commit()
    await db.refresh(s)
    background.add_task(style_sample_pipeline.run, async_session, s.id)
    return _to_summary(s)
```

> SQLite 默认不强制外键 CASCADE，需要在测试 engine 上开 `PRAGMA foreign_keys=ON`。检查 `backend/tests/conftest.py` 是否已开：
> 如果 `test_delete_cascades_chunks` 失败（chunk 没被删），需要在 `test_engine` fixture 加 listener：
> ```python
> from sqlalchemy import event
> @event.listens_for(engine.sync_engine, "connect")
> def _enable_fk(dbapi_conn, _):
>     dbapi_conn.execute("PRAGMA foreign_keys=ON")
> ```
> 但这是 conftest 改动，先跑测试看是否需要再决定。

- [ ] **Step 4: 跑测试**

```bash
cd backend && pytest tests/test_style_sample_router.py -v
```

预期：全部 PASS。如果 `test_delete_cascades_chunks` 失败，按上方提示在 `conftest.py` 的 `test_engine` fixture 加 `PRAGMA foreign_keys=ON` 后重跑。

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/style_sample.py backend/tests/test_style_sample_router.py
# 如果改了 conftest 也一并 add
git add backend/tests/conftest.py 2>/dev/null || true
git commit -m "feat(style-sample): DELETE(CASCADE) + POST reindex"
```

---

## Task 10：POST /search 语义检索

**Files:**
- Modify: `backend/app/routers/style_sample.py`
- Test: `backend/tests/test_style_sample_router.py`

- [ ] **Step 1: 追加 search 测试**

在测试文件末尾追加：

```python
from app.models.style_sample import StyleSampleChunk


@pytest.mark.asyncio
async def test_search_returns_top_k_grouped_by_sample(client, db_session, monkeypatch):
    """search 应按 sample 折叠去重，返回 (sample, top_chunks)"""
    guide = json.dumps({
        "structured": {"pov": "第一人称"}, "prose_excerpt": "...", "prompt_fragment": "frag"
    }, ensure_ascii=False)

    s1 = StyleSample(title="一", genre="都市言情", content="x", style_guide=guide, index_status="ready")
    s2 = StyleSample(title="二", genre="都市言情", content="y", style_guide=guide, index_status="ready")
    s3 = StyleSample(title="三 悬疑", genre="悬疑", content="z", style_guide=guide, index_status="ready")
    db_session.add_all([s1, s2, s3])
    await db_session.commit()
    for s in (s1, s2, s3):
        await db_session.refresh(s)

    # 给 s1 写 2 个 chunk、s2 写 1 个、s3 写 1 个
    db_session.add_all([
        StyleSampleChunk(sample_id=s1.id, chunk_index=0, content="一甲", char_count=2, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s1.id, chunk_index=1, content="一乙", char_count=2, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s2.id, chunk_index=0, content="二", char_count=1, embedding=[0.0] * 1536),
        StyleSampleChunk(sample_id=s3.id, chunk_index=0, content="三", char_count=1, embedding=[0.0] * 1536),
    ])
    await db_session.commit()

    # mock query embedding
    async def fake_embed(text):
        return [0.0] * 1536

    monkeypatch.setattr(
        "app.routers.style_sample.embedding_service.generate_embedding", fake_embed
    )

    # SQLite 不支持 pgvector 距离，测试里 service 必须有 SQLite 退化（按 sample 取最近 chunks 但不真排序）
    resp = client.post("/api/v1/style-samples/search", json={
        "query": "测试", "top_k": 5, "filter": {"genre": "都市言情"}
    })
    assert resp.status_code == 200
    hits = resp.json()
    titles = {h["sample"]["title"] for h in hits}
    assert titles == {"一", "二"}  # 题材过滤生效
    # 折叠：s1 的 2 个 chunk 应都在 top_chunks 里
    s1_hit = next(h for h in hits if h["sample"]["title"] == "一")
    assert len(s1_hit["top_chunks"]) == 2
    assert s1_hit["style_guide"]["prompt_fragment"] == "frag"


@pytest.mark.asyncio
async def test_search_empty_query_400(client):
    resp = client.post("/api/v1/style-samples/search", json={"query": "", "top_k": 5})
    assert resp.status_code == 422  # Pydantic min_length=1 触发
```

- [ ] **Step 2: 跑测试**

预期：FAIL（端点未实现）

- [ ] **Step 3: 实现 search**

在 `backend/app/routers/style_sample.py` 末尾追加：

```python
from sqlalchemy import text as _sql_text

from app.schemas.style_sample import SearchHit, SearchRequest
from app.services.embedding import embedding_service


def _is_postgres() -> bool:
    from app.core.config import settings
    return not settings.DATABASE_URL.startswith("sqlite")


@router.post("/search", response_model=list[SearchHit])
async def search_samples(
    payload: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query_vec = await embedding_service.generate_embedding(payload.query)
    genre_filter = payload.filter.get("genre") if isinstance(payload.filter, dict) else None

    if _is_postgres():
        # pgvector 余弦距离: <=> 越小越像；similarity = 1 - 距离
        sql = """
            SELECT c.sample_id, c.chunk_index, c.content, c.char_count,
                   1.0 - (c.embedding <=> CAST(:qv AS vector)) AS similarity
            FROM style_sample_chunks c
            JOIN style_samples s ON s.id = c.sample_id
            WHERE (:genre IS NULL OR s.genre = :genre)
              AND s.index_status = 'ready'
            ORDER BY c.embedding <=> CAST(:qv AS vector)
            LIMIT :lim
        """
        rows = (await db.execute(_sql_text(sql), {
            "qv": str(query_vec),  # pgvector accepts string form '[...]'
            "genre": genre_filter,
            "lim": payload.top_k * 5,  # 取多一点供 sample-level 折叠
        })).all()
        chunk_results = [
            {"sample_id": r.sample_id, "chunk_index": r.chunk_index,
             "content": r.content, "char_count": r.char_count, "similarity": float(r.similarity)}
            for r in rows
        ]
    else:
        # SQLite 退化路径：测试用,不真排序;只按 filter 取 ready 样本的 chunks
        stmt = select(StyleSampleChunk, StyleSample).join(
            StyleSample, StyleSample.id == StyleSampleChunk.sample_id
        ).where(StyleSample.index_status == "ready")
        if genre_filter:
            stmt = stmt.where(StyleSample.genre == genre_filter)
        rows = (await db.execute(stmt)).all()
        chunk_results = [
            {"sample_id": c.sample_id, "chunk_index": c.chunk_index,
             "content": c.content, "char_count": c.char_count, "similarity": 0.0}
            for (c, _s) in rows
        ]

    # 按 sample 折叠：每个 sample 最高分 chunk 决定排序,然后聚合该 sample 全部 hits
    by_sample: dict[int, list] = {}
    for r in chunk_results:
        by_sample.setdefault(r["sample_id"], []).append(r)

    # 取出对应 sample 行(批量),组装 SearchHit
    sample_ids = list(by_sample.keys())[: payload.top_k]
    samples = (await db.execute(
        select(StyleSample).where(StyleSample.id.in_(sample_ids))
    )).scalars().all()
    samples_by_id = {s.id: s for s in samples}

    hits: list[dict] = []
    for sid in sample_ids:
        s = samples_by_id.get(sid)
        if not s:
            continue
        top_chunks = sorted(by_sample[sid], key=lambda r: -r["similarity"])
        hits.append({
            "sample": _to_summary(s),
            "top_chunks": [{"chunk_index": c["chunk_index"], "content": c["content"],
                            "char_count": c["char_count"], "similarity": c["similarity"]}
                           for c in top_chunks],
            "style_guide": json.loads(s.style_guide) if s.style_guide else None,
        })
    return hits
```

- [ ] **Step 4: 跑测试**

```bash
cd backend && pytest tests/test_style_sample_router.py -v
```

预期：全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/style_sample.py backend/tests/test_style_sample_router.py
git commit -m "feat(style-sample): POST search (pgvector 余弦 + SQLite 退化)

Constraint: 按 sample 折叠去重,保证多样性
Directive: PG/SQLite 双路径——SQLite 仅供单测,不真排序
Confidence: medium
Scope-risk: narrow
Not-tested: PG 真实 1536 维 ranking 质量(集成测试单独覆盖)"
```

---

## Task 11：后端集成 smoke 验证

**Files:** 无新文件

- [ ] **Step 1: 跑全套后端测试，确认不破坏现有用例**

```bash
cd backend && pytest -v --tb=short 2>&1 | tail -50
```

预期：所有现有 + 新增测试 PASS（除已有的 `@pytest.mark.integration` 跳过）。

- [ ] **Step 2: 启动 dev 服务器，看 OpenAPI 包含新路由**

```bash
cd backend && uvicorn app.main:app --port 8888 &
sleep 3
curl -s http://localhost:8888/openapi.json | python -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(sorted(p for p in d['paths'] if 'style-sample' in p)))"
kill %1
```

预期输出包含：

```
/api/v1/style-samples
/api/v1/style-samples/search
/api/v1/style-samples/{sample_id}
/api/v1/style-samples/{sample_id}/reindex
```

- [ ] **Step 3: 提交（如有 lint 修正等小改）**

如有改动：

```bash
git add -A && git commit -m "chore(style-sample): 后端 smoke 通过"
```

若无改动，跳过提交。

---

## Task 12：前端 API 客户端

**Files:**
- Create: `frontend/src/api/styleSample.ts`

- [ ] **Step 1: 写 API 客户端**

写文件 `frontend/src/api/styleSample.ts`：

```typescript
import request from './request'

export type IndexStatus = 'pending' | 'indexing' | 'ready' | 'failed'

export interface StyleSampleSummary {
  id: number
  title: string
  author: string | null
  source: string | null
  genre: string | null
  tags: string | null
  total_chars: number
  index_status: IndexStatus
  index_error: string | null
  extracted_at: string | null
  created_at: string
  updated_at: string | null
}

export interface StyleGuideStructured {
  pov?: string
  tense?: string
  sentence_length?: string
  dialogue_density?: string
  pacing?: string
  opening_formula?: string
  ending_formula?: string
  signature_devices?: string[]
}

export interface StyleGuide {
  structured: StyleGuideStructured
  prose_excerpt: string
  prompt_fragment: string
}

export interface StyleSampleDetail extends StyleSampleSummary {
  file_path: string | null
  file_format: string | null
  notes: string | null
  content: string
  extraction_model: string | null
  style_guide: StyleGuide | null
}

export interface SearchHitChunk {
  chunk_index: number
  content: string
  char_count: number
  similarity: number
}

export interface SearchHit {
  sample: StyleSampleSummary
  top_chunks: SearchHitChunk[]
  style_guide: StyleGuide | null
}

export async function listStyleSamples(params?: { genre?: string }): Promise<StyleSampleSummary[]> {
  const qs = params?.genre ? `?genre=${encodeURIComponent(params.genre)}` : ''
  return request.get<StyleSampleSummary[]>(`/style-samples${qs}`)
}

export async function getStyleSample(id: number): Promise<StyleSampleDetail> {
  return request.get<StyleSampleDetail>(`/style-samples/${id}`)
}

export async function uploadStyleSample(
  file: File,
  meta: { title: string; author?: string; source?: string; genre?: string; tags?: string; notes?: string }
): Promise<StyleSampleSummary> {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('title', meta.title)
  if (meta.author) fd.append('author', meta.author)
  if (meta.source) fd.append('source', meta.source)
  if (meta.genre) fd.append('genre', meta.genre)
  if (meta.tags) fd.append('tags', meta.tags)
  if (meta.notes) fd.append('notes', meta.notes)
  return request.post<StyleSampleSummary>('/style-samples', fd)
}

export async function deleteStyleSample(id: number): Promise<void> {
  return request.delete<void>(`/style-samples/${id}`)
}

export async function reindexStyleSample(id: number): Promise<StyleSampleSummary> {
  return request.post<StyleSampleSummary>(`/style-samples/${id}/reindex`, {})
}

export async function searchStyleSamples(payload: {
  query: string
  top_k?: number
  filter?: Record<string, unknown>
}): Promise<SearchHit[]> {
  return request.post<SearchHit[]>('/style-samples/search', {
    top_k: 5,
    filter: {},
    ...payload,
  })
}
```

- [ ] **Step 2: 检查 TS 编译**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | head -20
```

预期：无新增 error（如果之前已有 baseline error 可以接受，但不应有 styleSample.ts 相关 error）

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/styleSample.ts
git commit -m "feat(style-sample): 前端 API 客户端"
```

---

## Task 13：StyleSampleLibrary.vue 主页面

**Files:**
- Create: `frontend/src/views/StyleSampleLibrary.vue`

- [ ] **Step 1: 写页面**

写文件 `frontend/src/views/StyleSampleLibrary.vue`：

```vue
<template>
  <div class="ssl-page">
    <!-- 顶栏 -->
    <div class="ssl-toolbar">
      <h2>知乎严选风格样本库</h2>
      <div class="ssl-toolbar-actions">
        <el-button type="primary" @click="uploadOpen = true">+ 上传样本</el-button>
        <el-button @click="refresh">刷新</el-button>
        <el-select v-model="genreFilter" placeholder="题材" clearable size="default" style="width: 180px" @change="refresh">
          <el-option v-for="g in genreOptions" :key="g" :label="g" :value="g" />
        </el-select>
      </div>
    </div>

    <!-- 列表 -->
    <el-table :data="samples" v-loading="loading" stripe>
      <el-table-column prop="title" label="标题" min-width="160" />
      <el-table-column prop="author" label="作者" width="100" />
      <el-table-column prop="source" label="来源" width="120" />
      <el-table-column prop="genre" label="题材" width="100" />
      <el-table-column prop="total_chars" label="字数" width="80" />
      <el-table-column label="索引状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.index_status)" effect="plain">
            {{ statusLabel(row.index_status) }}
          </el-tag>
          <el-tooltip v-if="row.index_status === 'failed'" :content="row.index_error || ''">
            <el-icon style="margin-left: 4px"><InfoFilled /></el-icon>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="extracted_at" label="抽取时间" width="180" />
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-button size="small" @click="openDetail(row.id)">详情</el-button>
          <el-button size="small" @click="onReindex(row)">重抽取</el-button>
          <el-popconfirm title="删除该样本？" @confirm="onDelete(row)">
            <template #reference><el-button size="small" type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadOpen" title="上传风格样本" width="560" @close="resetUpload">
      <el-form :model="uploadForm" label-width="80">
        <el-form-item label="文件" required>
          <el-upload
            :auto-upload="false"
            :on-change="onFileChange"
            :file-list="uploadFiles"
            :limit="1"
            accept=".txt,.md,.markdown,.docx"
          >
            <el-button>选择文件 (txt/md/docx)</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="标题" required><el-input v-model="uploadForm.title" /></el-form-item>
        <el-form-item label="作者"><el-input v-model="uploadForm.author" /></el-form-item>
        <el-form-item label="来源"><el-input v-model="uploadForm.source" placeholder="知乎严选 / 盐选 / 专栏名" /></el-form-item>
        <el-form-item label="题材">
          <el-select v-model="uploadForm.genre" placeholder="可选" clearable>
            <el-option v-for="g in genreOptions" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="标签"><el-input v-model="uploadForm.tags" placeholder='JSON 数组：["甜文","高糖"]' /></el-form-item>
        <el-form-item label="备注"><el-input v-model="uploadForm.notes" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="uploadOpen = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!canUpload" @click="onUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailOpen" :title="detailTitle" width="820">
      <div v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="作者">{{ detail.author || '—' }}</el-descriptions-item>
          <el-descriptions-item label="题材">{{ detail.genre || '—' }}</el-descriptions-item>
          <el-descriptions-item label="字数">{{ detail.total_chars }}</el-descriptions-item>
          <el-descriptions-item label="抽取 model">{{ detail.extraction_model || '—' }}</el-descriptions-item>
          <el-descriptions-item label="抽取时间">{{ detail.extracted_at || '—' }}</el-descriptions-item>
        </el-descriptions>

        <h4 style="margin-top: 16px">风格指南 — 结构化字段</h4>
        <el-descriptions v-if="detail.style_guide" :column="2" border size="small">
          <el-descriptions-item v-for="(v, k) in flatStructured(detail.style_guide.structured)" :key="k" :label="k">{{ v }}</el-descriptions-item>
        </el-descriptions>
        <el-empty v-else description="尚无抽取结果" :image-size="60" />

        <h4 style="margin-top: 16px">风格指南 — 典型节选 (prose_excerpt)</h4>
        <blockquote v-if="detail.style_guide?.prose_excerpt" class="ssl-quote">
          {{ detail.style_guide.prose_excerpt }}
        </blockquote>
        <el-empty v-else description="—" :image-size="40" />

        <h4 style="margin-top: 16px">
          风格指南 — Prompt 片段 (prompt_fragment)
          <el-button v-if="detail.style_guide?.prompt_fragment" size="small" link @click="copyFragment">复制</el-button>
        </h4>
        <pre v-if="detail.style_guide?.prompt_fragment" class="ssl-fragment">{{ detail.style_guide.prompt_fragment }}</pre>
        <el-empty v-else description="—" :image-size="40" />

        <el-collapse style="margin-top: 16px">
          <el-collapse-item title="原文全文" name="content">
            <pre class="ssl-content">{{ detail.content }}</pre>
          </el-collapse-item>
        </el-collapse>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { InfoFilled } from '@element-plus/icons-vue'
import {
  listStyleSamples, getStyleSample, uploadStyleSample,
  deleteStyleSample, reindexStyleSample,
  type StyleSampleSummary, type StyleSampleDetail, type StyleGuideStructured,
} from '@/api/styleSample'

const genreOptions = ['都市言情', '现代言情', '悬疑', '甜宠', '职场', '历史', '其他']

const samples = ref<StyleSampleSummary[]>([])
const loading = ref(false)
const genreFilter = ref<string>('')

const uploadOpen = ref(false)
const uploading = ref(false)
const uploadFiles = ref<{ raw: File }[]>([])
const uploadForm = ref({ title: '', author: '', source: '', genre: '', tags: '', notes: '' })

const detailOpen = ref(false)
const detail = ref<StyleSampleDetail | null>(null)
const detailTitle = computed(() => detail.value ? `详情：${detail.value.title}` : '详情')

let pollTimer: number | null = null

const canUpload = computed(() => uploadForm.value.title && uploadFiles.value.length === 1)

async function refresh() {
  loading.value = true
  try {
    samples.value = await listStyleSamples(genreFilter.value ? { genre: genreFilter.value } : undefined)
  } finally {
    loading.value = false
  }
  schedulePoll()
}

function schedulePoll() {
  if (pollTimer) { clearTimeout(pollTimer); pollTimer = null }
  const hasInflight = samples.value.some(s => s.index_status === 'pending' || s.index_status === 'indexing')
  if (hasInflight) {
    pollTimer = window.setTimeout(refresh, 5000)
  }
}

function statusTag(s: string) {
  return ({ pending: 'info', indexing: 'primary', ready: 'success', failed: 'danger' } as Record<string, 'info' | 'primary' | 'success' | 'danger'>)[s] || 'info'
}
function statusLabel(s: string) {
  return ({ pending: '待索引', indexing: '索引中', ready: '已就绪', failed: '失败' } as Record<string, string>)[s] || s
}

function onFileChange(file: { raw: File }) {
  uploadFiles.value = [file]
}

async function onUpload() {
  if (!canUpload.value) return
  uploading.value = true
  try {
    await uploadStyleSample(uploadFiles.value[0].raw, uploadForm.value)
    ElMessage.success('已上传，正在后台索引')
    uploadOpen.value = false
    resetUpload()
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.message || '上传失败')
  } finally {
    uploading.value = false
  }
}

function resetUpload() {
  uploadForm.value = { title: '', author: '', source: '', genre: '', tags: '', notes: '' }
  uploadFiles.value = []
}

async function openDetail(id: number) {
  detail.value = await getStyleSample(id)
  detailOpen.value = true
}

async function onDelete(row: StyleSampleSummary) {
  await deleteStyleSample(row.id)
  ElMessage.success('已删除')
  await refresh()
}

async function onReindex(row: StyleSampleSummary) {
  await reindexStyleSample(row.id)
  ElMessage.success('已触发重抽取')
  await refresh()
}

function flatStructured(s: StyleGuideStructured): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(s)) {
    if (v == null) continue
    out[k] = Array.isArray(v) ? v.join('、') : String(v)
  }
  return out
}

function copyFragment() {
  if (!detail.value?.style_guide) return
  navigator.clipboard.writeText(detail.value.style_guide.prompt_fragment)
  ElMessage.success('已复制')
}

onMounted(refresh)
onUnmounted(() => { if (pollTimer) clearTimeout(pollTimer) })
</script>

<style scoped>
.ssl-page { padding: 16px; }
.ssl-toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.ssl-toolbar-actions { display: flex; gap: 8px; align-items: center; }
.ssl-quote { background: var(--el-fill-color-light); padding: 12px; border-left: 3px solid var(--el-color-primary); margin: 8px 0; white-space: pre-wrap; }
.ssl-fragment { background: var(--el-fill-color-light); padding: 12px; white-space: pre-wrap; font-family: inherit; }
.ssl-content { max-height: 400px; overflow: auto; white-space: pre-wrap; font-family: inherit; }
</style>
```

- [ ] **Step 2: 跑 TS 检查**

```bash
cd frontend && npx vue-tsc --noEmit 2>&1 | grep -i "styleSampleLibrary\|styleSample" | head -10
```

预期：无 error。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/StyleSampleLibrary.vue
git commit -m "feat(style-sample): StyleSampleLibrary.vue 主页(列表/上传抽屉/详情弹窗)

Constraint: 全程上下堆叠+弹窗,不分屏(遵守 feedback_no_split_layout)
Confidence: high
Scope-risk: narrow"
```

---

## Task 14：路由 + 主页入口 + 端到端 smoke

**Files:**
- Modify: `frontend/src/router/index.ts`
- Modify: `frontend/src/views/ProjectListView.vue`

- [ ] **Step 1: 加路由**

修改 `frontend/src/router/index.ts`，在 `adaptation` 路由组之后（约 117 行附近）追加：

```typescript
  {
    path: '/style-samples',
    name: 'StyleSampleLibrary',
    component: () => import('@/views/StyleSampleLibrary.vue'),
    meta: { title: '风格样本库', requiresAuth: true },
  },
```

- [ ] **Step 2: 加首页 nav chip**

修改 `frontend/src/views/ProjectListView.vue`。找到 `$router.push('/adaptation')` 这一段（约 28 行），在那之后追加同样模式的按钮：

```vue
          <el-button @click="$router.push('/style-samples')" round>
            风格样本库
          </el-button>
```

具体看现有 4 个按钮的写法（drama/expansion/adaptation/...）跟着写。

- [ ] **Step 3: 启动前后端，端到端 smoke**

```bash
# terminal 1
cd backend && uvicorn app.main:app --port 8000 &
# terminal 2
cd frontend && npm run dev
```

浏览器开 `http://localhost:5173/projects` →
- 点 "风格样本库" → 进列表页（空）
- 点 "+ 上传样本" → 选一个 txt 文件 + 填标题 + 点上传
- 列表出现 status=indexing 行；5s 轮询后变 ready 或 failed
- 点 "详情" → 弹窗显示元数据 + 三段抽取产物
- 点 "重抽取" → 状态回到 pending → 再次轮询到 ready
- 点 "删除" → 行消失

**对照 spec Exit 标志**：上传 3-5 篇真实知乎严选样本，确认 `prompt_fragment` 人工通读"能直接拼 prompt"。

> 此步是验收，不是自动化测试。任何失败应在前一个 Task 内修复。

- [ ] **Step 4: 提交路由 + nav 改动**

```bash
git add frontend/src/router/index.ts frontend/src/views/ProjectListView.vue
git commit -m "feat(style-sample): 路由 + 首页 nav chip

Confidence: high
Scope-risk: narrow
Not-tested: 真实 LLM 抽出 prompt_fragment 是否符合\"剥离情节\"要求 — 由手工验收把关"
```

- [ ] **Step 5: 验收 commit**

完成 spec Exit 标志（3 篇真实样本通读）后：

```bash
git commit --allow-empty -m "chore(style-sample): Spec-1 完成 — 3 篇真实样本验收通过

Directive: Spec-2 可以开始,prompt_fragment 已被验证可直接用于下游 prompt 拼接"
```

---

## Self-review

- [x] **Spec 覆盖**：8 节 spec 全部映射到 task（节 1→T1, 节 2→T1-T11 模块边界, 节 3→T1, 节 4→T7-T10, 节 5→T5, 节 6→T3-T4, 节 7→T12-T14, 节 8→T11 + T14 验收）
- [x] **占位符**：无 TBD/TODO；每个 step 含可执行代码或命令
- [x] **类型一致**：`index_status` 全程是 `Literal['pending'|'indexing'|'ready'|'failed']` 字符串；`StyleSampleSummary` / `StyleSampleDetail` 在后端 Pydantic 与前端 TS 接口字段对齐
- [x] **不漏方法**：`_delete_chunks_only` 在 Task 4 写完 helper 后由 Task 6 pipeline 使用，路径正确

---

## 执行选择

Plan 完成保存到 `docs/superpowers/plans/2026-05-26-style-sample-library.md`。两种执行选择：

**1. Subagent-Driven（推荐）** —— 每个 task 派新 subagent 执行 + 两阶段 review，迭代快
**2. Inline Execution** —— 在本 session 执行 + checkpoints

任选其一。
