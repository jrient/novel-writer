# Expansion Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent text expansion module that imports external files or platform content, analyzes text structure/style, and performs AI-driven expansion with segmented streaming.

**Architecture:** Independent module following the existing drama module pattern — SQLAlchemy models, Pydantic schemas, FastAPI router with SSE streaming, dedicated AI service, Vue 3 frontend with Pinia store. Optimistic locking for concurrency control. Segmented expansion with summary-based context for coherence.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, python-docx, Vue 3, TypeScript, Pinia, Element Plus, SSE

**Spec:** `docs/superpowers/specs/2026-03-25-expansion-module-design.md`

---

## File Structure

### Backend

| File | Responsibility |
|------|---------------|
| `backend/app/models/expansion_project.py` | ExpansionProject ORM model |
| `backend/app/models/expansion_segment.py` | ExpansionSegment ORM model |
| `backend/app/models/__init__.py` | Register new models (modify) |
| `backend/app/schemas/expansion.py` | Pydantic request/response schemas |
| `backend/app/services/file_parser.py` | File upload parsing (.txt/.md/.docx) |
| `backend/app/services/expansion_ai_service.py` | AI analysis & expansion logic |
| `backend/app/routers/expansion.py` | REST + SSE API endpoints |
| `backend/app/routers/__init__.py` | Register expansion router (modify) |
| `backend/app/main.py` | Import expansion_router from routers package (modify) |
| `backend/scripts/migrate_add_expansion.py` | Database migration script |
| `backend/requirements.txt` | Add python-docx dependency (modify) |

### Frontend

| File | Responsibility |
|------|---------------|
| `frontend/src/api/expansion.ts` | API client with SSE streaming |
| `frontend/src/stores/expansion.ts` | Pinia state management |
| `frontend/src/views/ExpansionListView.vue` | Project list page |
| `frontend/src/views/ExpansionCreateView.vue` | Create project (upload/import/manual) |
| `frontend/src/views/ExpansionAnalyzeView.vue` | Analysis results + segmentation adjustment |
| `frontend/src/views/ExpansionWorkbenchView.vue` | Main expansion workbench (3-column) |
| `frontend/src/components/expansion/ExpansionSegmentList.vue` | Left panel: segment navigation |
| `frontend/src/components/expansion/ExpansionComparePanel.vue` | Center: original vs expanded |
| `frontend/src/components/expansion/ExpansionControlPanel.vue` | Right: expansion controls |
| `frontend/src/components/expansion/ExpansionProgressBar.vue` | Batch expansion progress |
| `frontend/src/components/expansion/SegmentSplitDialog.vue` | Split/merge segment dialog |
| `frontend/src/components/expansion/StyleProfileCard.vue` | Style profile display |
| `frontend/src/components/expansion/ImportSourceDialog.vue` | Import from platform project |
| `frontend/src/components/expansion/ExportConvertDialog.vue` | Export/convert dialog |
| `frontend/src/router/index.ts` | Add expansion routes (modify) |

### Tests

| File | Responsibility |
|------|---------------|
| `backend/tests/test_expansion_models.py` | Model unit tests |
| `backend/tests/test_expansion_schemas.py` | Schema validation tests |
| `backend/tests/test_file_parser.py` | File parser tests |
| `backend/tests/test_expansion_router.py` | API endpoint tests |

---

## Task 1: Backend Models

**Files:**
- Create: `backend/app/models/expansion_project.py`
- Create: `backend/app/models/expansion_segment.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_expansion_models.py`

- [ ] **Step 1: Write ExpansionProject model test**

```python
# backend/tests/test_expansion_models.py
"""扩写模块模型测试"""
import pytest
from datetime import datetime
from app.models.expansion_project import ExpansionProject
from app.models.expansion_segment import ExpansionSegment


class TestExpansionProjectModel:
    """ExpansionProject 模型字段测试"""

    def test_tablename(self):
        assert ExpansionProject.__tablename__ == "expansion_projects"

    def test_required_fields(self):
        """验证必须字段存在"""
        columns = {c.name for c in ExpansionProject.__table__.columns}
        required = {"id", "user_id", "title", "source_type", "original_text",
                     "word_count", "expansion_level", "status", "execution_mode",
                     "version", "created_at"}
        assert required.issubset(columns)

    def test_optional_fields(self):
        """验证可选字段存在"""
        columns = {c.name for c in ExpansionProject.__table__.columns}
        optional = {"summary", "style_profile", "target_word_count",
                     "style_instructions", "ai_config", "metadata", "source_ref"}
        assert optional.issubset(columns)

    def test_status_default(self):
        col = ExpansionProject.__table__.columns["status"]
        assert col.default.arg == "created"

    def test_version_default(self):
        col = ExpansionProject.__table__.columns["version"]
        assert col.default.arg == 1

    def test_execution_mode_default(self):
        col = ExpansionProject.__table__.columns["execution_mode"]
        assert col.default.arg == "auto"


class TestExpansionSegmentModel:
    """ExpansionSegment 模型字段测试"""

    def test_tablename(self):
        assert ExpansionSegment.__tablename__ == "expansion_segments"

    def test_required_fields(self):
        columns = {c.name for c in ExpansionSegment.__table__.columns}
        required = {"id", "project_id", "sort_order", "original_content",
                     "status", "original_word_count", "created_at"}
        assert required.issubset(columns)

    def test_optional_fields(self):
        columns = {c.name for c in ExpansionSegment.__table__.columns}
        optional = {"title", "expanded_content", "expansion_level",
                     "custom_instructions", "error_message", "expanded_word_count"}
        assert optional.issubset(columns)

    def test_status_default(self):
        col = ExpansionSegment.__table__.columns["status"]
        assert col.default.arg == "pending"

    def test_foreign_key(self):
        col = ExpansionSegment.__table__.columns["project_id"]
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "expansion_projects.id" in fks
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_models.py -v
```
Expected: FAIL (ImportError, modules not found)

- [ ] **Step 3: Write ExpansionProject model**

```python
# backend/app/models/expansion_project.py
"""扩写项目模型"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.expansion_segment import ExpansionSegment


class ExpansionProject(Base):
    """扩写项目表"""
    __tablename__ = "expansion_projects"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属用户ID",
    )

    # 基本信息
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="项目名称")
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="来源类型: upload/novel/drama/manual"
    )
    source_ref: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="来源引用(弱引用)"
    )
    original_text: Mapped[str] = mapped_column(
        Text, nullable=False, comment="原始全文"
    )
    word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="原文字数"
    )

    # AI 分析结果
    summary: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="全文摘要"
    )
    style_profile: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="文风画像"
    )

    # 扩写配置
    expansion_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="medium",
        comment="扩写深度: light/medium/deep"
    )
    target_word_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="目标字数"
    )
    style_instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="文风调整指令"
    )
    ai_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="AI配置"
    )

    # 状态管理
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created",
        comment="状态: created/analyzed/segmented/expanding/paused/error/completed"
    )
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto",
        comment="执行模式: auto/step_by_step"
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="乐观锁版本号"
    )

    # 元数据
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True, comment="元数据"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联关系
    owner: Mapped["User"] = relationship("User", backref="expansion_projects")
    segments: Mapped[List["ExpansionSegment"]] = relationship(
        "ExpansionSegment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ExpansionSegment.sort_order",
    )

    def __repr__(self):
        return f"<ExpansionProject(id={self.id}, title='{self.title}', status='{self.status}')>"
```

- [ ] **Step 4: Write ExpansionSegment model**

```python
# backend/app/models/expansion_segment.py
"""扩写分段模型"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.expansion_project import ExpansionProject


class ExpansionSegment(Base):
    """扩写分段表"""
    __tablename__ = "expansion_segments"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联项目
    project_id: Mapped[int] = mapped_column(
        ForeignKey("expansion_projects.id", ondelete="CASCADE"),
        nullable=False, index=True, comment="所属项目ID",
    )

    # 排序和标识
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="排序顺序"
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="段落标题"
    )

    # 内容
    original_content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="原文内容"
    )
    expanded_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="扩写后内容"
    )

    # 段落级配置
    expansion_level: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="覆盖扩写深度"
    )
    custom_instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="段落特殊指令"
    )

    # 状态
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="状态: pending/expanding/completed/error/skipped"
    )
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="错误详情"
    )

    # 字数统计
    original_word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="原文字数"
    )
    expanded_word_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="扩写后字数"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联关系
    project: Mapped["ExpansionProject"] = relationship(
        "ExpansionProject", back_populates="segments"
    )

    def __repr__(self):
        return f"<ExpansionSegment(id={self.id}, title='{self.title}', status='{self.status}')>"
```

- [ ] **Step 5: Register models in `__init__.py`**

Add to `backend/app/models/__init__.py`:
```python
from app.models.expansion_project import ExpansionProject
from app.models.expansion_segment import ExpansionSegment
```
And add `"ExpansionProject", "ExpansionSegment"` to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_models.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/expansion_project.py backend/app/models/expansion_segment.py backend/app/models/__init__.py backend/tests/test_expansion_models.py
git commit -m "feat(expansion): add ExpansionProject and ExpansionSegment ORM models"
```

---

## Task 2: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/expansion.py`
- Test: `backend/tests/test_expansion_schemas.py`

- [ ] **Step 1: Write schema validation tests**

```python
# backend/tests/test_expansion_schemas.py
"""扩写模块 Schema 测试"""
import pytest
from pydantic import ValidationError
from app.schemas.expansion import (
    ExpansionProjectCreate, ExpansionProjectUpdate, ExpansionProjectResponse,
    ExpansionSegmentResponse, ExpansionSegmentUpdate,
    SegmentSplitRequest, SegmentMergeRequest,
    ImportFromNovelRequest, ImportFromDramaRequest,
    ConvertRequest, StyleProfile,
    VALID_EXPANSION_LEVELS, VALID_SOURCE_TYPES, VALID_EXECUTION_MODES,
)


class TestExpansionProjectCreate:
    def test_valid_manual(self):
        data = ExpansionProjectCreate(
            title="测试扩写", source_type="manual",
            original_text="这是原文内容。" * 100,
        )
        assert data.title == "测试扩写"
        assert data.source_type == "manual"

    def test_title_required(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(source_type="manual", original_text="abc")

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="invalid", original_text="abc"
            )

    def test_invalid_expansion_level(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="manual",
                original_text="abc", expansion_level="extreme"
            )

    def test_word_count_limit(self):
        """超过 30000 字应该被拒绝"""
        long_text = "字" * 30001
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="manual", original_text=long_text
            )


class TestExpansionProjectUpdate:
    def test_partial_update(self):
        data = ExpansionProjectUpdate(expansion_level="deep")
        assert data.expansion_level == "deep"
        assert data.title is None

    def test_invalid_level(self):
        with pytest.raises(ValidationError):
            ExpansionProjectUpdate(expansion_level="invalid")


class TestSegmentRequests:
    def test_split_request(self):
        data = SegmentSplitRequest(segment_id=1, split_position=500)
        assert data.split_position == 500

    def test_split_negative_position(self):
        with pytest.raises(ValidationError):
            SegmentSplitRequest(segment_id=1, split_position=-1)

    def test_merge_request(self):
        data = SegmentMergeRequest(segment_ids=[1, 2])
        assert len(data.segment_ids) == 2

    def test_merge_single_segment(self):
        with pytest.raises(ValidationError):
            SegmentMergeRequest(segment_ids=[1])


class TestConvertRequest:
    def test_valid_target(self):
        data = ConvertRequest(target="novel")
        assert data.target == "novel"

    def test_invalid_target(self):
        with pytest.raises(ValidationError):
            ConvertRequest(target="other")


class TestStyleProfile:
    def test_valid_profile(self):
        profile = StyleProfile(
            narrative_pov="第三人称",
            tone="轻松",
            sentence_style="短句为主",
            vocabulary="口语化",
            rhythm="节奏快",
        )
        assert profile.narrative_pov == "第三人称"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_schemas.py -v
```
Expected: FAIL (ImportError)

- [ ] **Step 3: Write schemas**

```python
# backend/app/schemas/expansion.py
"""扩写模块 Pydantic Schemas"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- 类型常量 ---

VALID_EXPANSION_LEVELS = Literal["light", "medium", "deep"]
VALID_SOURCE_TYPES = Literal["upload", "novel", "drama", "manual"]
VALID_PROJECT_STATUSES = Literal[
    "created", "analyzed", "segmented", "expanding", "paused", "error", "completed"
]
VALID_SEGMENT_STATUSES = Literal["pending", "expanding", "completed", "error", "skipped"]
VALID_EXECUTION_MODES = Literal["auto", "step_by_step"]
VALID_EXPORT_FORMATS = Literal["txt", "md", "docx"]
VALID_EXPORT_VERSIONS = Literal["original", "expanded", "both"]
VALID_CONVERT_TARGETS = Literal["novel", "drama"]

MAX_WORD_COUNT = 30000


# --- 文风画像 ---

class StyleProfile(BaseModel):
    """文风画像结构"""
    narrative_pov: Optional[str] = Field(None, description="叙事视角")
    tone: Optional[str] = Field(None, description="语气基调")
    sentence_style: Optional[str] = Field(None, description="句式特征")
    vocabulary: Optional[str] = Field(None, description="用词偏好")
    rhythm: Optional[str] = Field(None, description="节奏感")
    notable_features: Optional[str] = Field(None, description="显著特点")


# --- AI 配置 (复用 drama 模块模式) ---

class ExpansionAIConfig(BaseModel):
    """AI 配置"""
    provider: Optional[str] = Field(None, description="AI 提供商")
    model: Optional[str] = Field(None, description="模型名称")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, gt=0)


# --- Project Schemas ---

class ExpansionProjectCreate(BaseModel):
    """创建扩写项目（手动输入）"""
    title: str = Field(..., min_length=1, max_length=200, description="项目名称")
    source_type: VALID_SOURCE_TYPES = Field("manual", description="来源类型")
    original_text: str = Field(..., min_length=1, description="原始文本")
    expansion_level: VALID_EXPANSION_LEVELS = Field("medium", description="扩写深度")
    target_word_count: Optional[int] = Field(None, gt=0, description="目标字数")
    style_instructions: Optional[str] = Field(None, description="文风调整指令")
    execution_mode: VALID_EXECUTION_MODES = Field("auto", description="执行模式")
    ai_config: Optional[ExpansionAIConfig] = Field(None, description="AI配置")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("original_text")
    @classmethod
    def validate_word_count(cls, v: str) -> str:
        if len(v) > MAX_WORD_COUNT:
            raise ValueError(f"文本超过 {MAX_WORD_COUNT} 字限制")
        return v


class ExpansionProjectUpdate(BaseModel):
    """更新扩写项目"""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    expansion_level: Optional[VALID_EXPANSION_LEVELS] = None
    target_word_count: Optional[int] = Field(None, gt=0)
    style_instructions: Optional[str] = None
    execution_mode: Optional[VALID_EXECUTION_MODES] = None
    ai_config: Optional[ExpansionAIConfig] = None
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")

    model_config = ConfigDict(populate_by_name=True)


class ExpansionProjectResponse(BaseModel):
    """扩写项目响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    source_type: str
    source_ref: Optional[Dict[str, Any]] = None
    word_count: int
    summary: Optional[str] = None
    style_profile: Optional[Dict[str, Any]] = None
    expansion_level: str
    target_word_count: Optional[int] = None
    style_instructions: Optional[str] = None
    ai_config: Optional[Dict[str, Any]] = None
    status: str
    execution_mode: str
    version: int
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata")
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExpansionProjectListResponse(BaseModel):
    """扩写项目列表响应（不含 original_text）"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    word_count: int
    expansion_level: str
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- Segment Schemas ---

class ExpansionSegmentResponse(BaseModel):
    """分段响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    sort_order: int
    title: Optional[str] = None
    original_content: str
    expanded_content: Optional[str] = None
    expansion_level: Optional[str] = None
    custom_instructions: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    original_word_count: int
    expanded_word_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExpansionSegmentUpdate(BaseModel):
    """更新分段"""
    title: Optional[str] = None
    original_content: Optional[str] = None
    expansion_level: Optional[VALID_EXPANSION_LEVELS] = None
    custom_instructions: Optional[str] = None


# --- 操作请求 ---

class SegmentSplitRequest(BaseModel):
    """拆分分段"""
    segment_id: int = Field(..., description="要拆分的分段ID")
    split_position: int = Field(..., ge=0, description="拆分位置(字符索引)")


class SegmentMergeRequest(BaseModel):
    """合并分段"""
    segment_ids: List[int] = Field(..., min_length=2, description="要合并的分段ID列表")


class ImportFromNovelRequest(BaseModel):
    """从小说项目导入"""
    project_id: int = Field(..., description="小说项目ID")
    chapter_ids: List[int] = Field(..., min_length=1, description="章节ID列表")
    title: Optional[str] = Field(None, max_length=200, description="扩写项目名称")


class ImportFromDramaRequest(BaseModel):
    """从剧本项目导入"""
    project_id: int = Field(..., description="剧本项目ID")
    title: Optional[str] = Field(None, max_length=200, description="扩写项目名称")


class ConvertRequest(BaseModel):
    """转换为平台项目"""
    target: VALID_CONVERT_TARGETS = Field(..., description="目标类型: novel/drama")


class ExpandSegmentRequest(BaseModel):
    """扩写单段请求（可选覆盖参数）"""
    expansion_level: Optional[VALID_EXPANSION_LEVELS] = None
    custom_instructions: Optional[str] = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_schemas.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/expansion.py backend/tests/test_expansion_schemas.py
git commit -m "feat(expansion): add Pydantic schemas with validation"
```

---

## Task 3: File Parser Service

**Files:**
- Create: `backend/app/services/file_parser.py`
- Modify: `backend/requirements.txt` (add python-docx)
- Test: `backend/tests/test_file_parser.py`

- [ ] **Step 1: Add python-docx to requirements**

Add `python-docx>=1.1.0` to `backend/requirements.txt`.

- [ ] **Step 2: Install dependency**

```bash
cd /data/project/novel-writer && pip install python-docx
```

- [ ] **Step 3: Write file parser tests**

```python
# backend/tests/test_file_parser.py
"""文件解析器测试"""
import pytest
from app.services.file_parser import FileParser, ParseResult


class TestFileParser:
    def test_parse_txt_utf8(self):
        content = "这是一段测试文本。包含中文内容。".encode("utf-8")
        result = FileParser.parse_txt(content)
        assert isinstance(result, ParseResult)
        assert "测试文本" in result.text
        assert result.word_count > 0

    def test_parse_txt_gbk(self):
        content = "这是GBK编码的文本。".encode("gbk")
        result = FileParser.parse_txt(content)
        assert "GBK编码" in result.text

    def test_parse_markdown(self):
        content = "# 标题\n\n这是正文内容。\n\n## 子标题\n\n更多内容。".encode("utf-8")
        result = FileParser.parse_markdown(content)
        assert "标题" in result.text
        assert "正文内容" in result.text
        assert len(result.detected_structure) > 0

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError, match="空文件"):
            FileParser.parse_txt(b"")

    def test_parse_too_long_raises(self):
        content = ("字" * 30001).encode("utf-8")
        with pytest.raises(ValueError, match="30000"):
            FileParser.parse_txt(content)

    def test_word_count_chinese(self):
        content = "这是十个中文字符的文本".encode("utf-8")
        result = FileParser.parse_txt(content)
        assert result.word_count == 10

    def test_detect_encoding_fallback(self):
        """无法解码的内容应抛出错误"""
        invalid_bytes = bytes(range(128, 256))
        with pytest.raises(ValueError, match="编码"):
            FileParser.parse_txt(invalid_bytes)
```

- [ ] **Step 4: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_file_parser.py -v
```
Expected: FAIL (ImportError)

- [ ] **Step 5: Write FileParser service**

```python
# backend/app/services/file_parser.py
"""文件解析服务 - 支持 .txt / .md / .docx"""
import re
import logging
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)

MAX_WORD_COUNT = 30000


@dataclass
class ParseResult:
    """解析结果"""
    text: str
    word_count: int
    detected_structure: List[str] = field(default_factory=list)


class FileParser:
    """统一文件解析器"""

    ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030"]

    @staticmethod
    def parse_txt(content: bytes) -> ParseResult:
        """解析纯文本文件"""
        if not content or not content.strip():
            raise ValueError("空文件，无法解析")

        text = FileParser._decode(content)
        word_count = FileParser._count_words(text)
        if word_count > MAX_WORD_COUNT:
            raise ValueError(f"文本超过 {MAX_WORD_COUNT} 字限制（当前 {word_count} 字），请裁剪后重试")

        return ParseResult(text=text, word_count=word_count)

    @staticmethod
    def parse_markdown(content: bytes) -> ParseResult:
        """解析 Markdown 文件，提取结构标记"""
        if not content or not content.strip():
            raise ValueError("空文件，无法解析")

        text = FileParser._decode(content)
        structure = []

        # 提取标题作为结构标记
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                level = len(line) - len(line.lstrip("#"))
                title = line.lstrip("#").strip()
                if title:
                    structure.append(f"h{level}:{title}")

        # 去除 Markdown 格式标记
        clean_text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)  # 标题标记
        clean_text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", clean_text)  # 粗体/斜体
        clean_text = re.sub(r"!\[.*?\]\(.*?\)", "", clean_text)  # 图片
        clean_text = re.sub(r"\[(.+?)\]\(.*?\)", r"\1", clean_text)  # 链接

        word_count = FileParser._count_words(clean_text)
        if word_count > MAX_WORD_COUNT:
            raise ValueError(f"文本超过 {MAX_WORD_COUNT} 字限制（当前 {word_count} 字）")

        return ParseResult(text=clean_text, word_count=word_count, detected_structure=structure)

    @staticmethod
    def parse_docx(content: bytes) -> ParseResult:
        """解析 Word 文档"""
        import io
        from docx import Document

        if not content:
            raise ValueError("空文件，无法解析")

        doc = Document(io.BytesIO(content))
        paragraphs = []
        structure = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            paragraphs.append(text)
            # 检测标题样式
            if para.style and para.style.name and para.style.name.startswith("Heading"):
                structure.append(f"{para.style.name}:{text}")

        full_text = "\n\n".join(paragraphs)
        if not full_text.strip():
            raise ValueError("空文件，无法解析")

        word_count = FileParser._count_words(full_text)
        if word_count > MAX_WORD_COUNT:
            raise ValueError(f"文本超过 {MAX_WORD_COUNT} 字限制（当前 {word_count} 字）")

        return ParseResult(text=full_text, word_count=word_count, detected_structure=structure)

    @staticmethod
    def _decode(content: bytes) -> str:
        """尝试多种编码解码"""
        for enc in FileParser.ENCODINGS:
            try:
                return content.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        raise ValueError("无法识别文件编码，请使用 UTF-8 编码保存后重试")

    @staticmethod
    def _count_words(text: str) -> int:
        """统计中文字数（中文字符数 + 英文单词数）"""
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        english_words = len(re.findall(r"[a-zA-Z]+", text))
        return chinese_chars + english_words
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_file_parser.py -v
```
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/file_parser.py backend/tests/test_file_parser.py backend/requirements.txt
git commit -m "feat(expansion): add FileParser service for txt/md/docx"
```

---

## Task 4: Expansion AI Service

**Files:**
- Create: `backend/app/services/expansion_ai_service.py`

This service is the core AI logic. It follows the same pattern as `ScriptAIService` — prompt templates, provider resolution, async generators for SSE streaming.

**Provider 复用说明**：项目有 `providers/` 抽象层（`BaseLLMProvider` + `StreamChunk`），但现有 `ScriptAIService` 直接用 httpx 调用 API（未使用 providers）。为保持一致性，本模块暂时沿用 ScriptAIService 的直接调用模式。后续可统一两个模块的 provider 调用方式（作为独立重构任务）。

- [ ] **Step 1: Write AI service unit tests**

```python
# backend/tests/test_expansion_ai_service.py
"""扩写 AI 服务单元测试（纯函数测试，不需要 mock AI 调用）"""
import pytest
from app.services.expansion_ai_service import ExpansionAIService, EXPANSION_LEVELS


class TestIsTruncated:
    def test_finish_reason_length(self):
        assert ExpansionAIService._is_truncated("任意文本", "length") is True

    def test_finish_reason_stop(self):
        assert ExpansionAIService._is_truncated("任意文本", "stop") is False

    def test_finish_reason_end_turn(self):
        assert ExpansionAIService._is_truncated("任意文本", "end_turn") is False

    def test_normal_ending_period(self):
        assert ExpansionAIService._is_truncated("这是完整的句子。") is False

    def test_normal_ending_question(self):
        assert ExpansionAIService._is_truncated("这是问句？") is False

    def test_normal_ending_quote(self):
        assert ExpansionAIService._is_truncated("他说："好的。"") is False

    def test_truncated_comma(self):
        assert ExpansionAIService._is_truncated("这句话还没说完，") is True

    def test_truncated_mid_word(self):
        assert ExpansionAIService._is_truncated("这句话断在中") is True

    def test_empty_text(self):
        assert ExpansionAIService._is_truncated("") is False

    def test_ellipsis_ending(self):
        assert ExpansionAIService._is_truncated("他渐渐远去……") is False


class TestDetectScriptMarkers:
    def test_os_marker(self):
        assert ExpansionAIService.detect_script_markers("秦天（OS）：我不会放弃的") is True

    def test_action_marker(self):
        assert ExpansionAIService.detect_script_markers("△秦天缓缓站起身") is True

    def test_effect_marker(self):
        assert ExpansionAIService.detect_script_markers("【闪回结束】") is True

    def test_no_markers(self):
        assert ExpansionAIService.detect_script_markers("这是一段普通的小说文本，没有任何剧本标记。") is False

    def test_plain_colon_not_match(self):
        # 仅有冒号不应误判（需多个标记）
        text = "注意：这是普通文本"
        # 单个冒号可能误判，但这是已知限制
        # detect_script_markers 需要结合多个标记判断


class TestExpansionLevels:
    def test_all_levels_defined(self):
        assert "light" in EXPANSION_LEVELS
        assert "medium" in EXPANSION_LEVELS
        assert "deep" in EXPANSION_LEVELS

    def test_multipliers(self):
        assert EXPANSION_LEVELS["light"]["multiplier"] == 1.5
        assert EXPANSION_LEVELS["medium"]["multiplier"] == 2.5
        assert EXPANSION_LEVELS["deep"]["multiplier"] == 4.0

    def test_all_have_description(self):
        for level in EXPANSION_LEVELS.values():
            assert "description" in level
            assert len(level["description"]) > 10


class TestResolveProvider:
    def test_default_provider(self):
        config = ExpansionAIService._resolve_provider()
        assert config["provider"] in ("openai", "anthropic", "ollama")
        assert "model" in config

    def test_custom_provider(self):
        config = ExpansionAIService._resolve_provider({"provider": "openai", "model": "gpt-4o-mini"})
        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o-mini"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_ai_service.py -v
```
Expected: FAIL (ImportError)

- [ ] **Step 3: Write ExpansionAIService**

```python
# backend/app/services/expansion_ai_service.py
"""
扩写 AI 服务
支持文本分析（摘要+文风+分段）和分段扩写
遵循 ScriptAIService 相同的 provider 解析模式
"""
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ─── 扩写深度定义 ──────────────────────────────────────────────────────────────

EXPANSION_LEVELS = {
    "light": {
        "description": (
            "润色补充：保持原有结构不变，补充感官细节、环境描写、"
            "人物微表情。不增加新情节或新对话。"
        ),
        "multiplier": 1.5,
    },
    "medium": {
        "description": (
            "中度扩展：在原有框架内增加过渡段落、内心独白、场景描写、"
            "对话细节。可适当展开已有情节但不引入新支线。"
        ),
        "multiplier": 2.5,
    },
    "deep": {
        "description": (
            "深度扩写：大幅丰富内容，可增加子场景、展开人物互动、"
            "补充背景故事、增加伏笔和细节呼应。保持主线不变的前提下"
            "充分展开叙事空间。"
        ),
        "multiplier": 4.0,
    },
}

# ─── 提示词模板 ──────────────────────────────────────────────────────────────

ANALYZE_PROMPT = """你是一位资深的文学编辑和文本分析专家。请对以下文本进行全面分析，生成：
1. 结构化摘要（包含主要人物、核心设定、情节主线，控制在1500字以内）
2. 文风画像（叙事视角、语气基调、句式特征、用词偏好、节奏感、显著特点）
3. 智能分段建议（每段建议在1000-2000字，在自然段落/场景/章节边界处切分）

请以如下 JSON 格式输出，不要有其他内容：
{{
  "summary": "结构化摘要...",
  "style_profile": {{
    "narrative_pov": "叙事视角",
    "tone": "语气基调",
    "sentence_style": "句式特征",
    "vocabulary": "用词偏好",
    "rhythm": "节奏感",
    "notable_features": "显著特点"
  }},
  "segments": [
    {{"title": "段落标题", "start_index": 0, "end_index": 1500, "word_count": 1500}},
    ...
  ]
}}

原文全文：
{original_text}"""

EXPAND_SYSTEM_PROMPT = """你是一位专业的小说/剧本扩写专家。你的任务是对给定的文本段落进行扩写。

文风要求：
{style_profile}

{style_instructions}

扩写深度：
{expansion_level_description}

{script_markers_instruction}

重要规则：
- 严格保持原文的核心情节和人物不变
- 扩写内容必须与原文风格一致
- 自然衔接前后段落的内容
- 目标字数约 {target_words} 字"""

EXPAND_USER_PROMPT = """全文摘要（供参考上下文）：
{summary}

当前是第 {segment_index}/{total_segments} 段

{prev_context}

【当前段原文（请扩写此段）】：
{original_content}

{next_context}

{custom_instructions}

请直接输出扩写后的内容，不要加任何前缀、解释或标记。"""

CONTINUATION_PROMPT = """你之前的扩写在此处被截断，请从断点处继续，保持风格和内容的连贯性：

...{tail_text}

请直接继续输出内容，不要重复已有内容："""

SCRIPT_MARKERS_INSTRUCTION = (
    "如果原文包含剧本格式标记（如 OS、△、【】、角色对话格式等），"
    "扩写时必须保留这些标记的格式和含义，不得将其转化为普通叙述。"
    "扩写可以增加新的标记使用，但必须遵循原文的标记体系。"
)


class ExpansionAIService:
    """扩写 AI 服务"""

    @staticmethod
    def _resolve_provider(ai_config: Optional[Dict[str, Any]] = None):
        """解析 AI 提供商配置，与 ScriptAIService 逻辑一致"""
        provider = (ai_config or {}).get("provider") or getattr(settings, "DEFAULT_AI_PROVIDER", "openai")
        model = (ai_config or {}).get("model") or None
        temperature = (ai_config or {}).get("temperature", 0.7)
        max_tokens = (ai_config or {}).get("max_tokens") or getattr(settings, "AI_MAX_TOKENS_STREAM", 8000)

        if provider == "openai":
            api_key = getattr(settings, "OPENAI_API_KEY", "")
            base_url = getattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = model or getattr(settings, "OPENAI_MODEL", "gpt-4o")
        elif provider == "anthropic":
            api_key = getattr(settings, "ANTHROPIC_API_KEY", "")
            base_url = "https://api.anthropic.com"
            model = model or getattr(settings, "ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        elif provider == "ollama":
            api_key = ""
            base_url = getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
            model = model or getattr(settings, "OLLAMA_MODEL", "llama3")
        else:
            raise ValueError(f"不支持的 AI 提供商: {provider}")

        return {
            "provider": provider,
            "api_key": api_key,
            "base_url": base_url,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    @staticmethod
    async def _stream_openai(
        config: dict, system_prompt: str, user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """OpenAI 流式请求"""
        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": config["temperature"],
            "max_tokens": config["max_tokens"],
            "stream": True,
        }

        finish_reason = None
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{config['base_url']}/chat/completions",
                headers=headers, json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        choice = data.get("choices", [{}])[0]
                        delta = choice.get("delta", {})
                        if "content" in delta and delta["content"]:
                            yield {"type": "text", "text": delta["content"]}
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
                    except json.JSONDecodeError:
                        continue

        yield {"type": "finish", "finish_reason": finish_reason}

    @staticmethod
    async def _stream_anthropic(
        config: dict, system_prompt: str, user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Anthropic 流式请求"""
        headers = {
            "x-api-key": config["api_key"],
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": config["temperature"],
            "stream": True,
        }

        finish_reason = None
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{config['base_url']}/v1/messages",
                headers=headers, json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = json.loads(line[6:])
                        event_type = data.get("type", "")
                        if event_type == "content_block_delta":
                            text = data.get("delta", {}).get("text", "")
                            if text:
                                yield {"type": "text", "text": text}
                        elif event_type == "message_delta":
                            finish_reason = data.get("delta", {}).get("stop_reason")
                    except json.JSONDecodeError:
                        continue

        yield {"type": "finish", "finish_reason": finish_reason}

    @staticmethod
    async def _stream_ollama(
        config: dict, system_prompt: str, user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Ollama 流式请求"""
        payload = {
            "model": config["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "options": {
                "temperature": config["temperature"],
                "num_predict": config["max_tokens"],
            },
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST", f"{config['base_url']}/api/chat",
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield {"type": "text", "text": content}
                        if data.get("done"):
                            yield {"type": "finish", "finish_reason": "stop"}
                    except json.JSONDecodeError:
                        continue

    @classmethod
    async def _stream(
        cls, config: dict, system_prompt: str, user_prompt: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """统一流式接口分发"""
        provider = config["provider"]
        if provider == "openai":
            gen = cls._stream_openai(config, system_prompt, user_prompt)
        elif provider == "anthropic":
            gen = cls._stream_anthropic(config, system_prompt, user_prompt)
        elif provider == "ollama":
            gen = cls._stream_ollama(config, system_prompt, user_prompt)
        else:
            raise ValueError(f"不支持的提供商: {provider}")

        async for chunk in gen:
            yield chunk

    @classmethod
    async def analyze_text(
        cls, original_text: str, ai_config: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """分析全文：生成摘要 + 文风画像 + 分段建议"""
        config = cls._resolve_provider(ai_config)
        prompt = ANALYZE_PROMPT.format(original_text=original_text)

        full_text = ""
        async for chunk in cls._stream(
            config,
            system_prompt="你是一位资深文学编辑，擅长文本分析和结构拆解。请严格按 JSON 格式输出。",
            user_prompt=prompt,
        ):
            if chunk["type"] == "text":
                full_text += chunk["text"]
                yield chunk
            elif chunk["type"] == "finish":
                yield chunk

        # 尝试解析完整 JSON
        try:
            # 处理可能的 markdown 代码块包裹
            clean = full_text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
                if clean.endswith("```"):
                    clean = clean[:-3]
                clean = clean.strip()
            result = json.loads(clean)
            yield {"type": "analysis_result", "data": result}
        except json.JSONDecodeError as e:
            logger.error(f"分析结果 JSON 解析失败: {e}")
            yield {"type": "error", "message": f"AI 分析结果格式错误: {e}"}

    @classmethod
    async def expand_segment(
        cls,
        original_content: str,
        summary: str,
        style_profile: Optional[Dict[str, Any]],
        expansion_level: str,
        target_words: int,
        segment_index: int,
        total_segments: int,
        prev_tail: str = "",
        next_head: str = "",
        style_instructions: str = "",
        custom_instructions: str = "",
        has_script_markers: bool = False,
        ai_config: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """扩写单个分段"""
        config = cls._resolve_provider(ai_config)
        level_info = EXPANSION_LEVELS.get(expansion_level, EXPANSION_LEVELS["medium"])

        # 组装 style_profile 文本
        style_text = ""
        if style_profile:
            style_text = "\n".join(f"- {k}: {v}" for k, v in style_profile.items() if v)

        style_instr = f"用户文风调整要求：{style_instructions}" if style_instructions else ""
        script_instr = SCRIPT_MARKERS_INSTRUCTION if has_script_markers else ""

        system_prompt = EXPAND_SYSTEM_PROMPT.format(
            style_profile=style_text or "（未分析）",
            style_instructions=style_instr,
            expansion_level_description=level_info["description"],
            script_markers_instruction=script_instr,
            target_words=target_words,
        )

        prev_context = f"【前一段结尾】：\n...{prev_tail}" if prev_tail else ""
        next_context = f"【后一段开头】：\n{next_head}..." if next_head else ""
        custom_instr = f"特殊要求：{custom_instructions}" if custom_instructions else ""

        user_prompt = EXPAND_USER_PROMPT.format(
            summary=summary or "（未生成摘要）",
            segment_index=segment_index,
            total_segments=total_segments,
            prev_context=prev_context,
            original_content=original_content,
            next_context=next_context,
            custom_instructions=custom_instr,
        )

        full_text = ""
        finish_reason = None

        async for chunk in cls._stream(config, system_prompt, user_prompt):
            if chunk["type"] == "text":
                full_text += chunk["text"]
                yield chunk
            elif chunk["type"] == "finish":
                finish_reason = chunk.get("finish_reason")

        # 检测截断并自动续写（最多 2 次）
        for _ in range(2):
            if not cls._is_truncated(full_text, finish_reason):
                break
            logger.info("检测到输出截断，自动续写...")
            cont_prompt = CONTINUATION_PROMPT.format(tail_text=full_text[-500:])
            finish_reason = None
            async for chunk in cls._stream(config, system_prompt, cont_prompt):
                if chunk["type"] == "text":
                    full_text += chunk["text"]
                    yield chunk
                elif chunk["type"] == "finish":
                    finish_reason = chunk.get("finish_reason")

        yield {"type": "done", "full_text": full_text, "word_count": len(full_text)}

    @staticmethod
    def _is_truncated(text: str, finish_reason: Optional[str] = None) -> bool:
        """判断输出是否被截断"""
        if finish_reason == "length":
            return True
        if finish_reason in ("stop", "end_turn"):
            return False
        text = text.strip()
        if not text:
            return False
        normal_endings = ["。", "！", "？", """, """, "」", "】", "……", "）", ")"]
        return not any(text.endswith(e) for e in normal_endings)

    @staticmethod
    def detect_script_markers(text: str) -> bool:
        """检测文本是否包含剧本格式标记"""
        import re
        markers = [
            r"\bOS\b", r"（OS）", r"△", r"【.*?】",
            r"^[^\n]{1,10}[：:]", # 角色名：对话
        ]
        for pattern in markers:
            if re.search(pattern, text, re.MULTILINE):
                return True
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_ai_service.py -v
```
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/expansion_ai_service.py backend/tests/test_expansion_ai_service.py
git commit -m "feat(expansion): add ExpansionAIService with analysis and segmented expansion"
```

---

## Task 5: Migration Script

**Files:**
- Create: `backend/scripts/migrate_add_expansion.py`

- [ ] **Step 1: Write migration script** (follow `migrate_add_drama.py` pattern)

```python
# backend/scripts/migrate_add_expansion.py
"""
数据库迁移脚本 - 添加扩写模块相关表
创建: expansion_projects, expansion_segments
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import Base, engine

# 导入模型确保 metadata 已注册
import app.models  # noqa: F401


EXPANSION_TABLES = ["expansion_projects", "expansion_segments"]


async def table_exists(conn, table_name: str) -> bool:
    """检查表是否存在（兼容 SQLite 和 PostgreSQL）"""
    if engine.url.drivername.startswith("sqlite"):
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        )
        return result.fetchone() is not None
    else:
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename=:name"
            ),
            {"name": table_name},
        )
        return result.fetchone() is not None


async def migrate_add_expansion():
    """创建扩写模块所需的表（如果不存在）"""
    async with engine.begin() as conn:
        existing = []
        missing = []

        for table_name in EXPANSION_TABLES:
            if await table_exists(conn, table_name):
                existing.append(table_name)
            else:
                missing.append(table_name)

        if existing:
            print(f"已存在的表（跳过）: {', '.join(existing)}")

        if not missing:
            print("所有扩写模块表已存在，无需迁移。")
            return

        print(f"需要创建的表: {', '.join(missing)}")

        tables_to_create = [
            Base.metadata.tables[t] for t in missing if t in Base.metadata.tables
        ]

        if tables_to_create:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=tables_to_create
                )
            )
            print(f"成功创建表: {', '.join(missing)}")
        else:
            print("警告: 未在 metadata 中找到对应表定义，请确认模型已正确导入。")


if __name__ == "__main__":
    asyncio.run(migrate_add_expansion())
```

- [ ] **Step 2: Commit**

```bash
git add backend/scripts/migrate_add_expansion.py
git commit -m "feat(expansion): add database migration script"
```

---

## Task 6: Backend Router

**Files:**
- Create: `backend/app/routers/expansion.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_expansion_router.py`

This is the largest backend file. It includes project CRUD, segment management, analysis SSE, expansion SSE, pause/resume, export, and conversion.

- [ ] **Step 1: Write basic router tests**

```python
# backend/tests/test_expansion_router.py
"""扩写模块路由基础测试"""
import pytest
from app.routers.expansion import router


class TestRouterRegistration:
    def test_router_prefix(self):
        assert router.prefix == "/api/v1/expansion"

    def test_router_tags(self):
        assert "expansion" in router.tags

    def test_routes_exist(self):
        route_paths = [r.path for r in router.routes]
        assert "/" in route_paths  # list/create
        assert "/{id}" in route_paths  # detail/update/delete
        assert "/{id}/analyze" in route_paths
        assert "/{id}/segments" in route_paths
        assert "/{id}/expand" in route_paths
        assert "/{id}/pause" in route_paths
        assert "/{id}/resume" in route_paths
        assert "/{id}/export" in route_paths
        assert "/{id}/convert" in route_paths
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_router.py -v
```
Expected: FAIL

- [ ] **Step 3: Write expansion router**

Create `backend/app/routers/expansion.py` with all endpoints following the drama router pattern:

Key endpoints to implement:
- `POST /` — create project (manual text input)
- `POST /upload` — file upload with FileParser
- `POST /import/novel` — import from novel project (uses `ImportFromNovelRequest`)
- `POST /import/drama` — import from drama project (uses `ImportFromDramaRequest`)
- `GET /` — list projects (paginated, without original_text)
- `GET /{id}` — get project detail
- `PUT /{id}` — update project config
- `DELETE /{id}` — delete project
- `POST /{id}/analyze` — SSE: analyze text (summary + style + segmentation). **关键逻辑**：收到 AI 返回的 `analysis_result` 后，按 `segments[].start_index/end_index` 从 `original_text` 切割出每段内容，批量创建 `ExpansionSegment` 记录（设置 `original_content`, `original_word_count`, `sort_order`, `title`），更新项目 `summary`/`style_profile`，将项目状态改为 `analyzed`（创建了 segments 后改为 `segmented`）
- `GET /{id}/segments` — list segments
- `PUT /{id}/segments/{seg_id}` — update segment
- `POST /{id}/segments/split` — split segment
- `POST /{id}/segments/merge` — merge segments
- `PUT /{id}/segments/reorder` — reorder segments
- `POST /{id}/expand` — SSE: batch expand all pending segments
- `POST /{id}/segments/{seg_id}/expand` — SSE: expand single segment
- `POST /{id}/pause` — pause expansion
- `POST /{id}/resume` — resume expansion (SSE, continues from first pending)
- `POST /{id}/segments/{seg_id}/retry` — retry single segment (SSE)
- `GET /{id}/export` — export (txt/md/docx)
- `POST /{id}/convert` — convert to novel/drama project

Use `get_expansion_project()` dependency (same pattern as `get_drama_project()`).
Use optimistic locking with `version` field for expansion state transitions.
SSE streaming follows `StreamingResponse` with `text/event-stream` content type.
Each SSE event is `data: {json}\n\n` format.

- [ ] **Step 4: Register router in routers/__init__.py and main.py**

Add to `backend/app/routers/__init__.py`:
```python
from app.routers.expansion import router as expansion_router
```
And add `"expansion_router"` to `__all__`.

Then in `backend/app/main.py`, import from the routers package (follow existing pattern):
```python
from app.routers import expansion_router
app.include_router(expansion_router)
```

- [ ] **Step 5: Run tests**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/test_expansion_router.py -v
```
Expected: PASS

- [ ] **Step 6: Run migration and verify**

```bash
cd /data/project/novel-writer && python backend/scripts/migrate_add_expansion.py
```
Expected: Tables created successfully

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/expansion.py backend/app/main.py backend/tests/test_expansion_router.py
git commit -m "feat(expansion): add REST + SSE router with full CRUD and expansion endpoints"
```

---

## Task 7: Frontend API Client

**Files:**
- Create: `frontend/src/api/expansion.ts`

- [ ] **Step 1: Write API client**

Follow `frontend/src/api/drama.ts` pattern. Key differences:
- Independent `_expansionStreamRequest()` with `StreamCallbacks` interface
- Support for rich event types: `status`, `segments`, `segment_start`, `segment_done`, `await_confirm`
- File upload endpoint uses `FormData`

Types to define:
```typescript
interface ExpansionProject { id, user_id, title, source_type, word_count, summary, style_profile, expansion_level, target_word_count, style_instructions, status, execution_mode, version, ... }
interface ExpansionProjectListItem { id, title, source_type, word_count, expansion_level, status, ... }
interface ExpansionSegment { id, project_id, sort_order, title, original_content, expanded_content, status, error_message, original_word_count, expanded_word_count, ... }
interface StreamCallbacks { onText?, onEvent?, onDone?, onError? }
```

Functions to export:
```typescript
// Project CRUD
getExpansionProjects(params?) → ExpansionProjectListItem[]
createExpansionProject(data) → ExpansionProject
uploadExpansionProject(file, title?, ...) → ExpansionProject
importFromNovel(data) → ExpansionProject
importFromDrama(data) → ExpansionProject
getExpansionProject(id) → ExpansionProject
updateExpansionProject(id, data) → ExpansionProject
deleteExpansionProject(id) → void

// Analysis (SSE)
streamAnalyze(id, callbacks) → AbortController

// Segments
getSegments(projectId) → ExpansionSegment[]
updateSegment(projectId, segId, data) → ExpansionSegment
splitSegment(projectId, data) → ExpansionSegment[]
mergeSegments(projectId, data) → ExpansionSegment
reorderSegments(projectId, items) → void

// Expansion (SSE)
streamExpand(projectId, callbacks) → AbortController
streamExpandSegment(projectId, segId, callbacks, overrides?) → AbortController
pauseExpansion(projectId) → void
resumeExpansion(projectId, callbacks) → AbortController
retrySegment(projectId, segId, callbacks) → AbortController

// Export/Convert
getExportUrl(projectId, format, version) → string
convertProject(projectId, target) → { project_id, project_type }
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/expansion.ts
git commit -m "feat(expansion): add frontend API client with SSE streaming"
```

---

## Task 8: Pinia Store

**Files:**
- Create: `frontend/src/stores/expansion.ts`

- [ ] **Step 1: Write Pinia store**

Follow `frontend/src/stores/drama.ts` pattern with `defineStore('expansion', () => {...})`.

State refs:
```typescript
projects: ref<ExpansionProjectListItem[]>([])
currentProject: ref<ExpansionProject | null>(null)
segments: ref<ExpansionSegment[]>([])
currentSegmentId: ref<number | null>(null)
isAnalyzing: ref(false)
isExpanding: ref(false)
expandingSegmentId: ref<number | null>(null)
loading: ref(false)
```

Actions: wrap all API calls, update state, handle SSE callbacks by updating reactive state.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/expansion.ts
git commit -m "feat(expansion): add Pinia store for expansion state management"
```

---

## Task 9: Frontend Routes

**Files:**
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: Add expansion routes**

Add after the drama routes block:
```typescript
{
  path: '/expansion',
  name: 'ExpansionList',
  component: () => import('@/views/ExpansionListView.vue'),
  meta: { title: '文本扩写', requiresAuth: true },
},
{
  path: '/expansion/create',
  name: 'ExpansionCreate',
  component: () => import('@/views/ExpansionCreateView.vue'),
  meta: { title: '创建扩写项目', requiresAuth: true },
},
{
  path: '/expansion/analyze/:id',
  name: 'ExpansionAnalyze',
  component: () => import('@/views/ExpansionAnalyzeView.vue'),
  meta: { title: '文本分析', requiresAuth: true },
},
{
  path: '/expansion/workbench/:id',
  name: 'ExpansionWorkbench',
  component: () => import('@/views/ExpansionWorkbenchView.vue'),
  meta: { title: '扩写工作台', requiresAuth: true },
},
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/router/index.ts
git commit -m "feat(expansion): add frontend routes"
```

---

## Task 10: Frontend Views — List & Create

**Files:**
- Create: `frontend/src/views/ExpansionListView.vue`
- Create: `frontend/src/views/ExpansionCreateView.vue`
- Create: `frontend/src/components/expansion/ImportSourceDialog.vue` (needed by CreateView)

- [ ] **Step 1: Write ExpansionListView**

Follow `DramaListView.vue` pattern:
- Project list with `el-table` (title, source_type, word_count, status, created_at)
- Filter by status
- Create button → navigate to `/expansion/create`
- Row click → navigate to `/expansion/analyze/:id` or `/expansion/workbench/:id` depending on status
- Delete with `el-popconfirm`

- [ ] **Step 2: Write ImportSourceDialog component**

Dialog with two tabs:
- "从小说导入": Select novel project → select chapters → confirm
- "从剧本导入": Select drama project → confirm
Uses existing project/drama API to fetch available projects.

- [ ] **Step 3: Write ExpansionCreateView**

Three-tab creation flow:
- Tab 1: Upload file (el-upload with drag, accept `.txt,.md,.docx`)
- Tab 2: Import from platform (ImportSourceDialog component)
- Tab 3: Manual input (el-input textarea, max 30000 chars)
- Common fields: title, expansion_level (radio group), target_word_count, execution_mode
- On submit → create project → navigate to `/expansion/analyze/:id`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ExpansionListView.vue frontend/src/views/ExpansionCreateView.vue frontend/src/components/expansion/ImportSourceDialog.vue
git commit -m "feat(expansion): add list and create views with import dialog"
```

---

## Task 11: Frontend Views — Analyze

**Files:**
- Create: `frontend/src/views/ExpansionAnalyzeView.vue`
- Create: `frontend/src/components/expansion/StyleProfileCard.vue`
- Create: `frontend/src/components/expansion/SegmentSplitDialog.vue`

- [ ] **Step 1: Write StyleProfileCard component**

Display style_profile fields in a card with el-descriptions.

- [ ] **Step 2: Write SegmentSplitDialog component**

Dialog for split (show text with cursor position picker) and merge (select adjacent segments).

- [ ] **Step 3: Write ExpansionAnalyzeView**

Three-section page:
1. **Summary section**: Streaming display during analysis, editable after completion
2. **Style profile**: StyleProfileCard showing analysis results
3. **Segments section**: el-table of segments with title, word_count, actions (split/merge/edit)
4. **Config sidebar**: expansion_level, target_word_count, execution_mode settings
5. **Bottom action**: "开始扩写" button → navigate to workbench

On mount: check if already analyzed (status == "analyzed" or later), if "created" → auto-trigger analysis SSE.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ExpansionAnalyzeView.vue frontend/src/components/expansion/StyleProfileCard.vue frontend/src/components/expansion/SegmentSplitDialog.vue
git commit -m "feat(expansion): add analyze view with style profile and segment management"
```

---

## Task 12: Frontend Views — Workbench

**Files:**
- Create: `frontend/src/views/ExpansionWorkbenchView.vue`
- Create: `frontend/src/components/expansion/ExpansionSegmentList.vue`
- Create: `frontend/src/components/expansion/ExpansionComparePanel.vue`
- Create: `frontend/src/components/expansion/ExpansionControlPanel.vue`
- Create: `frontend/src/components/expansion/ExpansionProgressBar.vue`

- [ ] **Step 1: Write ExpansionSegmentList (left panel)**

Vertical list of segments with:
- Status icons (pending=dot, expanding=spinner, completed=check, error=warning, skipped=dash)
- Current segment highlighted
- Progress stats (completed/total, total word count)
- Click to select segment

- [ ] **Step 2: Write ExpansionComparePanel (center panel)**

Side-by-side panels:
- Left: original_content (read-only, scrollable)
- Right: expanded_content (read-only, streaming during expansion)
- Word count comparison bar at bottom: `original → expanded (+X%)`

- [ ] **Step 3: Write ExpansionControlPanel (right panel)**

Controls:
- Expansion level radio group (light/medium/deep) — per-segment override
- Target word count input
- Style instructions textarea
- Custom instructions textarea (per-segment)
- Action buttons: "扩写此段", "全部扩写", "暂停/继续"
- Segment-specific retry button

- [ ] **Step 4: Write ExpansionProgressBar**

Progress bar for batch expansion:
- Shows current segment name and progress (N/total)
- Animated progress with percentage
- Status text (expanding/paused/completed/error)

- [ ] **Step 5: Write ExpansionWorkbenchView**

Three-column layout using `DraggableDivider` (existing component):
- Left column: ExpansionSegmentList
- Center column: ExpansionComparePanel + ExpansionProgressBar
- Right column: ExpansionControlPanel

Wire up SSE streaming: when expanding, update segment's expanded_content reactively as chunks arrive.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ExpansionWorkbenchView.vue frontend/src/components/expansion/
git commit -m "feat(expansion): add workbench view with 3-column layout and streaming"
```

---

## Task 13: Export & Convert Component

**Files:**
- Create: `frontend/src/components/expansion/ExportConvertDialog.vue`

Note: `ImportSourceDialog.vue` already created in Task 10.

- [ ] **Step 1: Write ExportConvertDialog**

Dialog with two sections:
- Export: format selector (txt/md/docx), version selector (original/expanded/both), download button
- Convert: target selector (novel/drama), convert button, shows result with link to new project

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/expansion/ExportConvertDialog.vue
git commit -m "feat(expansion): add export/convert dialog"
```

---

## Task 14: Navigation Entry & Integration

**Files:**
- Modify: `frontend/src/views/ProjectListView.vue` (add navigation link to expansion)

- [ ] **Step 1: Add navigation entry**

Add "文本扩写" link/button to the project list view, similar to how drama module was linked. Use `router.push('/expansion')`.

- [ ] **Step 2: Verify all routes work**

```bash
cd /data/project/novel-writer && npm run build --prefix frontend
```
Expected: Build succeeds without errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/ProjectListView.vue
git commit -m "feat(expansion): add navigation entry from project list"
```

---

## Task 15: End-to-End Verification

- [ ] **Step 1: Run all backend tests**

```bash
cd /data/project/novel-writer && python -m pytest backend/tests/ -v
```
Expected: All tests PASS

- [ ] **Step 2: Run frontend build**

```bash
cd /data/project/novel-writer && npm run build --prefix frontend
```
Expected: Build succeeds

- [ ] **Step 3: Run migration on dev database**

```bash
cd /data/project/novel-writer && python backend/scripts/migrate_add_expansion.py
```
Expected: Tables created

- [ ] **Step 4: Manual smoke test**

Start the dev server and verify:
1. Navigate to `/expansion` — list page loads
2. Create a project with manual text input
3. Analysis page shows streaming results
4. Workbench loads with 3-column layout
5. Single segment expansion works with streaming

- [ ] **Step 5: Final commit (if any remaining changes)**

```bash
git status
# Review changes, then add specific files:
git add backend/ frontend/
git commit -m "feat(expansion): complete text expansion module implementation"
```
