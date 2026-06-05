# 原作知识图谱（Canon Knowledge Graph）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 canon 设定提取系统上叠加「实体关系边抽取 + 图谱可视化检阅」，把扁平实体清单升级为真·知识图谱。

**Architecture:** 维度 6→10；新增 `CanonRelation` 边表（新表，靠 `Base.metadata.create_all` 自动建，无 Alembic）；在 `run_canon_extraction` 实体 PERSIST 之后追加 `RELATION_EXTRACT` 阶段抽三元组并落库；新增关系/图谱 API；`ReferenceCanonView` 加「图谱视图」Tab，用 `relation-graph-vue3` 渲染。

**Tech Stack:** FastAPI + SQLAlchemy(async) + PostgreSQL；Vue3 + TS + Element Plus + relation-graph-vue3；pytest + pytest-asyncio（SQLite 内存库）。

**约定（沿用现有范式）：**
- LLM 调用：`await AIService.generate_text(prompt, provider=model, max_tokens=4000)`
- JSON 容错：`_safe_json_array(raw)`（已在 `canon_pipeline.py`）
- SSE：`await canon_event_bus.publish(reference_id, {...})`
- 测试：`backend/tests/test_canon_*.py`；router 用 `client` + 自定义 `ref` fixture；pipeline/relation 用 `unittest.mock.patch(..., AsyncMock)` mock `AIService.generate_text`
- 后端测试命令：`cd backend && python -m pytest tests/<file>::<test> -v`
- 提交：分支 `feat/canon-knowledge-graph`（已存在）；conventional commit `feat(canon): ...` / `test(canon): ...`

---

## File Structure

**后端（修改）：**
- `backend/app/models/canon.py` — 新增 `CanonRelation` 模型
- `backend/app/schemas/canon.py` — 新增 4 个 schema
- `backend/app/services/canon_prompts.py` — 维度扩 10 + 关系词表 + `build_relation_prompt`
- `backend/app/services/canon_pipeline.py` — `ENTITY_TYPES` 扩 10 + 关系抽取阶段 + 标准 relation 函数 + 接线
- `backend/app/services/canon_context.py` — `_TYPE_CN` 扩 10（关系注入留 follow-up）
- `backend/app/routers/canon.py` — 新增关系 CRUD + graph + extract-relations 端点

**后端（测试，新增/扩展）：**
- `backend/tests/test_canon_prompts.py` — 加关系 prompt 测试
- `backend/tests/test_canon_models.py` — 加 CanonRelation 模型测试
- `backend/tests/test_canon_schemas.py` — 加关系 schema 测试
- `backend/tests/test_canon_relations.py`（新）— 关系抽取纯函数（解析/回链/去重）
- `backend/tests/test_canon_router.py` — 加关系 CRUD + graph + extract-relations 路由测试

**前端（修改/新增）：**
- `frontend/package.json` — 加 `relation-graph-vue3`
- `frontend/src/api/canon.ts` — 维度 union 扩 10 + 关系类型 + 关系/图谱 API
- `frontend/src/components/canon/CanonGraphView.vue`（新）— 图谱组件
- `frontend/src/views/ReferenceCanonView.vue` — 加 Tab + 10 维度标签/配色

---

## Phase A — 维度扩展 6→10

### Task A1: prompts 维度枚举扩到 10

**Files:**
- Modify: `backend/app/services/canon_prompts.py`
- Test: `backend/tests/test_canon_prompts.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_prompts.py` 末尾）

```python
def test_atomic_prompt_includes_new_dimensions():
    p = build_atomic_prompt(chunk_text="他取出一件法宝", chunk_label="片段1")
    for key in ("item", "race", "realm", "concept"):
        assert key in p
    # 中文维度名也应出现在类型说明里
    assert "物品" in p and "种族" in p and "境界" in p and "术语" in p
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py::test_atomic_prompt_includes_new_dimensions -v`
Expected: FAIL（`item` 等不在 prompt 中）

- [ ] **Step 3: 实现**

在 `canon_prompts.py` 把 `ENTITY_TYPES_CN` 补全为 10 类：

```python
ENTITY_TYPES_CN = {
    "character": "角色（人物）",
    "location": "地点（地名/场所）",
    "ability": "能力（功法/法术/技能）",
    "faction": "势力（门派/国家/组织）",
    "worldrule": "世界观规则（修炼体系/天道法则/社会设定）",
    "event": "关键事件（推动剧情的重大事件）",
    "item": "物品（法宝/神器/丹药/功法秘籍等实体道具）",
    "race": "种族/血脉（人族/妖族/魔族/血脉传承）",
    "realm": "境界/体系（修为境界/等级体系，如练气→筑基）",
    "concept": "专有术语（设定专名，非上述具体物）",
}
```

把 `ATOMIC_SYSTEM` 开头「分为六类」段改为十类，并更新 `entity_type` 枚举值：

```python
ATOMIC_SYSTEM = """你是一位严谨的原作设定分析专家。请从给定的小说片段中，只提取【本片段明确出现】的设定信息，分为十类：
角色(character)/地点(location)/能力(ability)/势力(faction)/世界观规则(worldrule)/关键事件(event)/物品(item)/种族血脉(race)/境界体系(realm)/专有术语(concept)。

【铁律——防止幻觉】
1. 只提取片段中【确有文字依据】的设定，严禁脑补、严禁补充原作其他章节的知识。
2. 每一条设定都必须附带 source（原文引用片段 quote，≤40字，从片段中原样摘录）。
3. 无法确定的字段留空，不要编造。

严格输出 JSON 数组，每个元素格式：
{
  "entity_type": "character|location|ability|faction|worldrule|event|item|race|realm|concept",
  "canonical_name": "设定名",
  "aliases": ["别名/称呼"],
  "summary": "一句话设定（仅依据本片段）",
  "attributes": {"任意键": "值"},
  "source": {"quote": "原文摘录≤40字"},
  "importance": "critical|major|minor"
}
只输出 JSON 数组，不要任何解释文字。"""
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py -v`
Expected: 全部 PASS（含原有 2 个用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_prompts.py backend/tests/test_canon_prompts.py
git commit -m "feat(canon): atomic/merge prompt 维度扩展至 10 类"
```

### Task A2: pipeline 与 context 的维度常量同步

**Files:**
- Modify: `backend/app/services/canon_pipeline.py:33`（`ENTITY_TYPES`）
- Modify: `backend/app/services/canon_context.py`（`_TYPE_CN`）
- Test: `backend/tests/test_canon_context.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_context.py`）

```python
def test_type_cn_covers_ten_dimensions():
    from app.services.canon_context import _TYPE_CN
    for key in ("item", "race", "realm", "concept"):
        assert key in _TYPE_CN
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_context.py::test_type_cn_covers_ten_dimensions -v`
Expected: FAIL

- [ ] **Step 3: 实现**

`canon_pipeline.py` 顶部：

```python
ENTITY_TYPES = ["character", "location", "ability", "faction", "worldrule",
                "event", "item", "race", "realm", "concept"]
```

`canon_context.py` 的 `_TYPE_CN`：

```python
_TYPE_CN = {
    "character": "人物", "location": "地点", "ability": "能力",
    "faction": "势力", "worldrule": "世界观规则", "event": "关键事件",
    "item": "物品", "race": "种族血脉", "realm": "境界体系", "concept": "专有术语",
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_context.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/app/services/canon_context.py backend/tests/test_canon_context.py
git commit -m "feat(canon): ENTITY_TYPES 与 context 维度常量同步至 10"
```

---

## Phase B — CanonRelation 模型与 schema

### Task B1: CanonRelation 模型

**Files:**
- Modify: `backend/app/models/canon.py`（文件末尾追加）
- Test: `backend/tests/test_canon_models.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_models.py`）

```python
@pytest.mark.asyncio
async def test_canon_relation_persist(db_session):
    from app.models.reference import ReferenceNovel
    from app.models.canon import CanonEntity, CanonRelation
    ref = ReferenceNovel(title="原作", content="正文", total_chars=2)
    db_session.add(ref); await db_session.commit(); await db_session.refresh(ref)
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="乙")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)
    rel = CanonRelation(
        reference_id=ref.id, source_entity_id=a.id, target_entity_id=b.id,
        relation_type="师徒", label="甲是乙的师父",
        source_refs=[{"chapter": "片段1", "quote": "甲收乙为徒"}],
    )
    db_session.add(rel); await db_session.commit(); await db_session.refresh(rel)
    assert rel.id is not None
    assert rel.review_status == "ai_extracted"
    assert rel.confidence == 1.0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_models.py::test_canon_relation_persist -v`
Expected: FAIL（`ImportError: cannot import name 'CanonRelation'`）

- [ ] **Step 3: 实现**（追加到 `backend/app/models/canon.py`，复用文件顶部已有的 import：`String, Text, Integer, Float, ForeignKey, JSON, Mapped, mapped_column, utcnow_naive, Base`）

```python
class CanonRelation(Base):
    """原作知识图谱的关系边（三元组 <source, relation, target>）"""
    __tablename__ = "canon_relations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("reference_novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_entity_id: Mapped[int] = mapped_column(
        ForeignKey("canon_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_entity_id: Mapped[int] = mapped_column(
        ForeignKey("canon_entities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # 受控词表 key（见 canon_prompts.RELATION_TYPES_CN）或 "custom"
    relation_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 溯源：[{"chapter": "片段N", "quote": "≤40字原文"}]
    source_refs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # ai_extracted / user_verified / user_edited / user_added
    review_status: Mapped[str] = mapped_column(String(20), default="ai_extracted")

    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=utcnow_naive)

    def __repr__(self):
        return f"<CanonRelation(id={self.id}, type='{self.relation_type}', {self.source_entity_id}->{self.target_entity_id})>"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_models.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/canon.py backend/tests/test_canon_models.py
git commit -m "feat(canon): 新增 CanonRelation 关系边模型"
```

### Task B2: 关系 schema

**Files:**
- Modify: `backend/app/schemas/canon.py`（末尾追加）
- Test: `backend/tests/test_canon_schemas.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_schemas.py`）

```python
def test_canon_relation_schemas():
    from app.schemas.canon import (
        CanonRelationOut, CanonRelationCreate, CanonRelationUpdate, CanonGraphOut,
    )
    c = CanonRelationCreate(source_entity_id=1, target_entity_id=2,
                            relation_type="师徒", label="甲是乙的师父")
    assert c.relation_type == "师徒"
    u = CanonRelationUpdate(review_status="user_verified")
    assert u.label is None
    g = CanonGraphOut(nodes=[], edges=[])
    assert g.nodes == [] and g.edges == []
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_schemas.py::test_canon_relation_schemas -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现**（追加到 `backend/app/schemas/canon.py`，复用顶部已有 import：`datetime, Optional, List, Dict, Any, BaseModel, ConfigDict, Field`；`CanonEntityOut` 已在本文件定义）

```python
class CanonRelationOut(BaseModel):
    id: int
    reference_id: int
    source_entity_id: int
    target_entity_id: int
    relation_type: str
    label: Optional[str] = None
    summary: Optional[str] = None
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float
    review_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CanonRelationCreate(BaseModel):
    source_entity_id: int
    target_entity_id: int
    relation_type: str
    label: Optional[str] = None
    summary: Optional[str] = None
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)


class CanonRelationUpdate(BaseModel):
    relation_type: Optional[str] = None
    label: Optional[str] = None
    summary: Optional[str] = None
    review_status: Optional[str] = None


class CanonGraphOut(BaseModel):
    nodes: List[CanonEntityOut] = Field(default_factory=list)
    edges: List[CanonRelationOut] = Field(default_factory=list)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_schemas.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/schemas/canon.py backend/tests/test_canon_schemas.py
git commit -m "feat(canon): 关系与图谱 schema"
```

---

## Phase C — 关系抽取（prompt + 纯函数 + pipeline 接线）

### Task C1: 关系受控词表 + build_relation_prompt

**Files:**
- Modify: `backend/app/services/canon_prompts.py`
- Test: `backend/tests/test_canon_prompts.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_prompts.py`）

```python
def test_relation_prompt_lists_entities_and_vocab():
    from app.services.canon_prompts import build_relation_prompt, RELATION_TYPES_CN
    entities = [
        {"id": 1, "canonical_name": "甲", "entity_type": "character"},
        {"id": 2, "canonical_name": "乙", "entity_type": "character"},
    ]
    p = build_relation_prompt(entities=entities, chunk_text="甲收乙为徒。", chunk_label="片段1")
    assert "甲" in p and "乙" in p           # 实体清单注入
    assert "师徒" in p                        # 受控词表注入
    assert "custom" in p                      # 自由文本兜底说明
    assert "片段1" in p
    assert "师徒" in RELATION_TYPES_CN
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py::test_relation_prompt_lists_entities_and_vocab -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现**（追加到 `canon_prompts.py`）

```python
# 受控关系词表：key 为存储值，value 为说明
RELATION_TYPES_CN = {
    "亲属": "角色↔角色：血缘/姻亲",
    "师徒": "角色↔角色：师承",
    "情感": "角色↔角色：恋慕/夫妻/挚友",
    "盟友": "角色↔角色 或 势力↔势力：结盟",
    "敌对": "角色/势力之间：敌对仇杀",
    "上下级": "角色↔角色：统属/主从",
    "属于": "角色→势力/种族：归属",
    "领导": "角色→势力：领导/掌门",
    "创立": "角色→势力：开创",
    "出身": "角色→地点：出生地/来历",
    "居于": "角色→地点：居所",
    "统治": "角色→地点/势力：治理",
    "掌握": "角色→能力：习得功法/技能",
    "持有": "角色→物品：拥有",
    "炼制": "角色→物品：炼制/创造",
    "处于境界": "角色→境界：当前修为",
    "参与": "角色→事件：参与",
    "主导": "角色→事件：主导/发动",
    "受害": "角色→事件：受害方",
    "承载": "物品→能力：法宝赋予能力",
    "记载": "物品→能力：秘籍记载功法",
    "天赋": "种族→能力：天生能力",
    "进阶": "境界→境界：层级递进",
    "因果": "事件→事件：因果",
    "时序": "事件→事件：先后",
    "伏笔": "事件→事件：伏笔呼应",
    "发生于": "事件→地点：发生地",
    "隶属": "势力→势力 或 地点→地点：层级隶属",
    "custom": "以上都不匹配时，用自由文本 label 描述关系",
}

RELATION_SYSTEM = """你是一位严谨的原作关系分析专家。下面给你【本部原作已确认的设定实体清单】和【一个原文片段】。
请只在【清单内实体之间】抽取本片段中【有文字依据】的关系，形成三元组。

【铁律】
1. source 与 target 必须是清单里的 canonical_name，严禁出现清单外的名字。
2. 只抽本片段确有依据的关系，严禁脑补；每条须附 quote（原文摘录≤40字）。
3. relation_type 优先取受控词表的 key；都不匹配时填 "custom" 并在 label 写明关系。

严格输出 JSON 数组，元素格式：
{
  "source": "清单中的 canonical_name",
  "target": "清单中的 canonical_name",
  "relation_type": "受控词表 key 或 custom",
  "label": "关系简述（custom 必填，其它可选）",
  "quote": "原文摘录≤40字"
}
只输出 JSON 数组，不要任何解释文字。"""


def build_relation_prompt(entities: list, chunk_text: str, chunk_label: str) -> str:
    vocab = "\n".join(f"- {k}：{v}" for k, v in RELATION_TYPES_CN.items())
    ent_lines = "\n".join(
        f"- {e.get('canonical_name')}（{e.get('entity_type')}）" for e in entities
    )
    return (
        f"{RELATION_SYSTEM}\n\n"
        f"【受控关系词表】\n{vocab}\n\n"
        f"【实体清单】\n{ent_lines}\n\n"
        f"【片段位置】{chunk_label}\n【片段正文】\n{chunk_text}\n\n"
        f"请输出本片段实体间的关系 JSON 数组（每条含 quote）："
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_prompts.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_prompts.py backend/tests/test_canon_prompts.py
git commit -m "feat(canon): 关系受控词表 + build_relation_prompt"
```

### Task C2: 关系解析/回链/去重纯函数

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`（新增纯函数，放在 `run_canon_extraction` 之前）
- Test: `backend/tests/test_canon_relations.py`（新建）

- [ ] **Step 1: 写失败测试**（新建 `backend/tests/test_canon_relations.py`）

```python
"""关系抽取纯函数：name→id 回链 + 去重"""
from app.services.canon_pipeline import _build_name_index, _resolve_relations


def test_build_name_index_includes_aliases():
    ents = [
        {"id": 1, "canonical_name": "孙悟空", "aliases": ["猴哥", "齐天大圣"]},
        {"id": 2, "canonical_name": "唐僧", "aliases": []},
    ]
    idx = _build_name_index(ents)
    assert idx["孙悟空"] == 1
    assert idx["猴哥"] == 1
    assert idx["齐天大圣"] == 1
    assert idx["唐僧"] == 2


def test_resolve_relations_links_and_dedups():
    ents = [
        {"id": 1, "canonical_name": "孙悟空", "aliases": ["猴哥"]},
        {"id": 2, "canonical_name": "唐僧", "aliases": []},
    ]
    idx = _build_name_index(ents)
    raw = [
        {"source": "唐僧", "target": "猴哥", "relation_type": "师徒",
         "label": "唐僧是孙悟空的师父", "quote": "拜为师父"},
        # 重复（同 source/target/type）应被合并
        {"source": "唐僧", "target": "孙悟空", "relation_type": "师徒",
         "label": "", "quote": "师徒同行"},
        # 清单外实体应被丢弃
        {"source": "牛魔王", "target": "唐僧", "relation_type": "敌对", "quote": "x"},
        # 自指应被丢弃
        {"source": "唐僧", "target": "唐僧", "relation_type": "custom", "quote": "x"},
    ]
    rels = _resolve_relations(raw, idx, chunk_label="片段1")
    assert len(rels) == 1
    r = rels[0]
    assert r["source_entity_id"] == 2 and r["target_entity_id"] == 1
    assert r["relation_type"] == "师徒"
    # 两条来源 quote 都保留
    assert len(r["source_refs"]) == 2
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_relations.py -v`
Expected: FAIL（ImportError）

- [ ] **Step 3: 实现**（加到 `canon_pipeline.py`，`build_relation_prompt` 需 import）

在文件顶部 import 区补：

```python
from app.services.canon_prompts import build_atomic_prompt, build_merge_prompt, build_relation_prompt
```

新增纯函数：

```python
def _build_name_index(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    """canonical_name 与 aliases → entity_id。后者不覆盖前者已占用的名字。"""
    idx: Dict[str, int] = {}
    for e in entities:
        eid = e.get("id")
        name = (e.get("canonical_name") or "").strip()
        if name and name not in idx:
            idx[name] = eid
        for a in e.get("aliases") or []:
            a = (a or "").strip()
            if a and a not in idx:
                idx[a] = eid
    return idx


def _resolve_relations(
    raw_rels: List[Dict[str, Any]], name_index: Dict[str, int], chunk_label: str
) -> List[Dict[str, Any]]:
    """把 LLM 抽出的 {source,target,...} 回链到 entity_id，丢弃越界/自指，并按
    (src,tgt,type) 去重合并 source_refs。"""
    bucket: Dict[tuple, Dict[str, Any]] = {}
    for r in raw_rels:
        if not isinstance(r, dict):
            continue
        sid = name_index.get((r.get("source") or "").strip())
        tid = name_index.get((r.get("target") or "").strip())
        if sid is None or tid is None or sid == tid:
            continue
        rtype = (r.get("relation_type") or "custom").strip() or "custom"
        key = (sid, tid, rtype)
        quote = (r.get("quote") or "").strip()
        ref = {"chapter": chunk_label, "quote": quote} if quote else None
        if key in bucket:
            if ref:
                bucket[key]["source_refs"].append(ref)
        else:
            bucket[key] = {
                "source_entity_id": sid,
                "target_entity_id": tid,
                "relation_type": rtype,
                "label": (r.get("label") or "").strip() or None,
                "summary": None,
                "source_refs": [ref] if ref else [],
            }
    return list(bucket.values())
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_relations.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_relations.py
git commit -m "feat(canon): 关系回链与去重纯函数"
```

### Task C3: 关系抽取阶段函数（带 SSE）+ 持久化

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`
- Test: `backend/tests/test_canon_relations.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_relations.py`；mock `AIService.generate_text` 返回固定关系 JSON）

```python
import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy import select


@pytest.mark.asyncio
async def test_extract_and_persist_relations(db_session):
    from app.models.reference import ReferenceNovel
    from app.models.canon import CanonEntity, CanonRelation
    from app.services import canon_pipeline as cp

    ref = ReferenceNovel(title="原作", content="唐僧收孙悟空为徒。", total_chars=8)
    db_session.add(ref); await db_session.commit(); await db_session.refresh(ref)
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="唐僧")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="孙悟空", aliases=["猴哥"])
    db_session.add_all([a, b]); await db_session.commit()

    fake = '[{"source":"唐僧","target":"孙悟空","relation_type":"师徒","label":"师父","quote":"收为徒"}]'
    from sqlalchemy.ext.asyncio import async_sessionmaker
    sf = async_sessionmaker(db_session.bind, expire_on_commit=False)
    with patch.object(cp.AIService, "generate_text", new=AsyncMock(return_value=fake)):
        n = await cp.extract_relations_for_reference(ref.id, sf, model=None)
    assert n == 1
    rows = (await db_session.execute(select(CanonRelation).where(
        CanonRelation.reference_id == ref.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].relation_type == "师徒"
    assert rows[0].review_status == "ai_extracted"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_relations.py::test_extract_and_persist_relations -v`
Expected: FAIL（`extract_relations_for_reference` 不存在）

- [ ] **Step 3: 实现**（加到 `canon_pipeline.py`；复用 `_chunk_reference`、`ENTITY_TYPES`、`canon_event_bus`、`_safe_json_array`、`ATOMIC_CONCURRENCY`；新增 import：`from app.models.canon import CanonEntity, CanonExtractionJob, CanonRelation`——把 `CanonRelation` 加入已有 import 行）

```python
async def _relation_extract_chunk(
    chunk: Dict[str, str], entities_brief: List[Dict[str, Any]],
    name_index: Dict[str, int], model: Optional[str],
) -> List[Dict[str, Any]]:
    prompt = build_relation_prompt(
        entities=entities_brief, chunk_text=chunk["text"], chunk_label=chunk["label"])
    raw = await AIService.generate_text(prompt, provider=model, max_tokens=4000)
    return _resolve_relations(_safe_json_array(raw), name_index, chunk["label"])


async def extract_relations_for_reference(
    reference_id: int, session_factory: async_sessionmaker, model: Optional[str] = None,
) -> int:
    """对已存在实体的 reference 抽关系并落库。返回关系数。
    幂等：清空既有 ai_extracted 关系，保留 user_*。会发 relation_* SSE 事件。"""
    # 取实体 + 原文
    async with session_factory() as s:
        ref = (await s.execute(select(ReferenceNovel).where(
            ReferenceNovel.id == reference_id))).scalar_one_or_none()
        if ref is None:
            raise ValueError(f"reference {reference_id} 不存在")
        content = ref.content or ""
        ents = (await s.execute(select(CanonEntity).where(
            CanonEntity.reference_id == reference_id))).scalars().all()
        entities_brief = [
            {"id": e.id, "canonical_name": e.canonical_name,
             "entity_type": e.entity_type, "aliases": e.aliases or []}
            for e in ents
        ]
    if not entities_brief:
        return 0

    name_index = _build_name_index(entities_brief)
    chunks = _chunk_reference(content)
    await canon_event_bus.publish(reference_id, {
        "event": "relation_chunked", "relation_total": len(chunks)})

    sem = asyncio.Semaphore(ATOMIC_CONCURRENCY)
    done = 0
    all_rels: List[Dict[str, Any]] = []

    async def _worker(ch):
        nonlocal done
        async with sem:
            try:
                rels = await _relation_extract_chunk(ch, entities_brief, name_index, model)
            except Exception as e:  # noqa: BLE001
                logger.warning("canon relation chunk failed: %s", e)
                rels = []
            all_rels.extend(rels)
            done += 1
            await canon_event_bus.publish(reference_id, {
                "event": "relation_progress", "relation_done": done,
                "relation_total": len(chunks)})

    await asyncio.gather(*[_worker(c) for c in chunks])

    # 跨块再去重合并（同 src,tgt,type）
    merged: Dict[tuple, Dict[str, Any]] = {}
    for r in all_rels:
        key = (r["source_entity_id"], r["target_entity_id"], r["relation_type"])
        if key in merged:
            merged[key]["source_refs"].extend(r["source_refs"])
            if not merged[key]["label"] and r["label"]:
                merged[key]["label"] = r["label"]
        else:
            merged[key] = r
    final = list(merged.values())

    async with session_factory() as s:
        if final:
            await s.execute(delete(CanonRelation).where(
                CanonRelation.reference_id == reference_id,
                CanonRelation.review_status == "ai_extracted"))
            for r in final:
                s.add(CanonRelation(
                    reference_id=reference_id,
                    source_entity_id=r["source_entity_id"],
                    target_entity_id=r["target_entity_id"],
                    relation_type=r["relation_type"][:40],
                    label=(r["label"] or None),
                    summary=r.get("summary"),
                    source_refs=r["source_refs"],
                    review_status="ai_extracted",
                ))
            await s.commit()
    return len(final)
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_relations.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_relations.py
git commit -m "feat(canon): 关系抽取阶段函数 extract_relations_for_reference + 落库"
```

### Task C4: 接入主提取管线（实体落库后自动抽关系）

**Files:**
- Modify: `backend/app/services/canon_pipeline.py`（`run_canon_extraction` 的 PERSIST 之后、`done` 事件之前）
- Test: `backend/tests/test_canon_pipeline.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_pipeline.py`；让 atomic 返回两个角色、relation 返回一条师徒）

```python
@pytest.mark.asyncio
async def test_run_extraction_also_builds_relations(db_session):
    from app.models.reference import ReferenceNovel
    from app.models.canon import CanonRelation
    from app.services import canon_pipeline as cp
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlalchemy import select

    ref = ReferenceNovel(title="原作", content="唐僧收孙悟空为徒。", total_chars=8)
    db_session.add(ref); await db_session.commit(); await db_session.refresh(ref)

    atomic = ('[{"entity_type":"character","canonical_name":"唐僧","source":{"quote":"唐僧"},"importance":"major"},'
              '{"entity_type":"character","canonical_name":"孙悟空","source":{"quote":"孙悟空"},"importance":"major"}]')
    merge = ('[{"entity_type":"character","canonical_name":"唐僧","aliases":[],"source_refs":[{"quote":"x"}],"importance":"major"},'
             '{"entity_type":"character","canonical_name":"孙悟空","aliases":[],"source_refs":[{"quote":"x"}],"importance":"major"}]')
    rel = '[{"source":"唐僧","target":"孙悟空","relation_type":"师徒","label":"师父","quote":"收为徒"}]'

    async def fake_generate(prompt, *a, **k):
        if "关系分析" in prompt:   # build_relation_prompt 的 RELATION_SYSTEM 关键词
            return rel
        if "归并" in prompt:       # MERGE_SYSTEM 关键词
            return merge
        return atomic

    sf = async_sessionmaker(db_session.bind, expire_on_commit=False)
    from unittest.mock import patch
    with patch.object(cp.AIService, "generate_text", side_effect=fake_generate):
        await cp.run_canon_extraction(ref.id, sf, model=None)

    rows = (await db_session.execute(select(CanonRelation).where(
        CanonRelation.reference_id == ref.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].relation_type == "师徒"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py::test_run_extraction_also_builds_relations -v`
Expected: FAIL（关系表为空）

- [ ] **Step 3: 实现**

在 `run_canon_extraction` 中，PERSIST 实体的 `async with session_factory() as s:` 块结束、`await canon_event_bus.publish(reference_id, {"event": "done", ...})` 之前，插入：

```python
        # 6) RELATION_EXTRACT（实体已落库，按已存实体抽关系）
        try:
            relation_count = await extract_relations_for_reference(
                reference_id, session_factory, model)
        except Exception:  # noqa: BLE001
            logger.exception("canon relation extraction failed (non-fatal)")
            relation_count = 0
```

并把结尾 `done` 事件改为带 relation_count：

```python
        await canon_event_bus.publish(reference_id,
            {"event": "done", "job_id": job_id, "entity_count": new_count,
             "relation_count": relation_count})
```

- [ ] **Step 4: 运行确认通过 + canon 全回归**

Run: `cd backend && python -m pytest tests/test_canon_pipeline.py tests/test_canon_relations.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/canon_pipeline.py backend/tests/test_canon_pipeline.py
git commit -m "feat(canon): 主提取管线在实体落库后自动抽取关系"
```

---

## Phase D — API 端点

### Task D1: 关系 CRUD 路由

**Files:**
- Modify: `backend/app/routers/canon.py`
- Test: `backend/tests/test_canon_router.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_router.py`；复用其 `ref` fixture）

```python
@pytest.mark.asyncio
async def test_relation_crud(client, ref, db_session):
    from app.models.canon import CanonEntity
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="乙")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)

    # create
    r = client.post(f"/api/v1/references/{ref.id}/canon/relations", json={
        "source_entity_id": a.id, "target_entity_id": b.id,
        "relation_type": "师徒", "label": "甲是乙的师父"})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert r.json()["review_status"] == "user_added"

    # list
    r = client.get(f"/api/v1/references/{ref.id}/canon/relations")
    assert r.status_code == 200 and len(r.json()) == 1

    # update → user_edited
    r = client.put(f"/api/v1/references/{ref.id}/canon/relations/{rid}",
                   json={"label": "改了"})
    assert r.status_code == 200 and r.json()["label"] == "改了"
    assert r.json()["review_status"] == "user_edited"

    # delete
    r = client.delete(f"/api/v1/references/{ref.id}/canon/relations/{rid}")
    assert r.status_code == 204
    r = client.get(f"/api/v1/references/{ref.id}/canon/relations")
    assert len(r.json()) == 0
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_router.py::test_relation_crud -v`
Expected: FAIL（404，路由不存在）

- [ ] **Step 3: 实现**（加到 `routers/canon.py`；扩 import：`from app.models.canon import CanonEntity, CanonExtractionJob, CanonRelation`；`from app.schemas.canon import (... , CanonRelationOut, CanonRelationCreate, CanonRelationUpdate, CanonGraphOut)`；新增 `from app.services.canon_pipeline import run_canon_extraction, extract_relations_for_reference`）

```python
@router.get("/relations", response_model=list[CanonRelationOut])
async def list_relations(
    reference_id: int,
    relation_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    stmt = select(CanonRelation).where(CanonRelation.reference_id == reference_id)
    if relation_type:
        stmt = stmt.where(CanonRelation.relation_type == relation_type)
    rows = (await db.execute(stmt.order_by(CanonRelation.id))).scalars().all()
    return rows


@router.post("/relations", response_model=CanonRelationOut, status_code=201)
async def create_relation(
    reference_id: int,
    payload: CanonRelationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    r = CanonRelation(
        reference_id=reference_id,
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        relation_type=payload.relation_type,
        label=payload.label,
        summary=payload.summary,
        source_refs=payload.source_refs,
        review_status="user_added",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


@router.put("/relations/{relation_id}", response_model=CanonRelationOut)
async def update_relation(
    reference_id: int,
    relation_id: int,
    payload: CanonRelationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    r = (await db.execute(select(CanonRelation).where(
        CanonRelation.id == relation_id,
        CanonRelation.reference_id == reference_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="关系不存在")
    data = payload.model_dump(exclude_unset=True)
    explicit_status = data.pop("review_status", None)
    for k, v in data.items():
        setattr(r, k, v)
    r.review_status = explicit_status or "user_edited"
    await db.commit()
    await db.refresh(r)
    return r


@router.delete("/relations/{relation_id}", status_code=204)
async def delete_relation(
    reference_id: int,
    relation_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    r = (await db.execute(select(CanonRelation).where(
        CanonRelation.id == relation_id,
        CanonRelation.reference_id == reference_id))).scalar_one_or_none()
    if r is None:
        raise HTTPException(status_code=404, detail="关系不存在")
    await db.delete(r)
    await db.commit()
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && python -m pytest tests/test_canon_router.py -v`
Expected: PASS（含原有用例）

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/canon.py backend/tests/test_canon_router.py
git commit -m "feat(canon): 关系 CRUD 路由"
```

### Task D2: graph 端点 + extract-relations 端点

**Files:**
- Modify: `backend/app/routers/canon.py`
- Test: `backend/tests/test_canon_router.py`

- [ ] **Step 1: 写失败测试**（追加到 `test_canon_router.py`）

```python
@pytest.mark.asyncio
async def test_graph_endpoint(client, ref, db_session):
    from app.models.canon import CanonEntity, CanonRelation
    a = CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲")
    b = CanonEntity(reference_id=ref.id, entity_type="faction", canonical_name="某派")
    db_session.add_all([a, b]); await db_session.commit()
    await db_session.refresh(a); await db_session.refresh(b)
    db_session.add(CanonRelation(reference_id=ref.id, source_entity_id=a.id,
                                 target_entity_id=b.id, relation_type="属于"))
    await db_session.commit()
    r = client.get(f"/api/v1/references/{ref.id}/canon/graph")
    assert r.status_code == 200
    body = r.json()
    assert len(body["nodes"]) == 2 and len(body["edges"]) == 1


@pytest.mark.asyncio
async def test_extract_relations_requires_entities(client, ref):
    # 无实体时拒绝
    r = client.post(f"/api/v1/references/{ref.id}/canon/extract-relations")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_extract_relations_triggers(client, ref, db_session):
    from unittest.mock import patch, AsyncMock
    from app.models.canon import CanonEntity
    db_session.add(CanonEntity(reference_id=ref.id, entity_type="character", canonical_name="甲"))
    await db_session.commit()
    with patch("app.routers.canon.extract_relations_for_reference",
               new=AsyncMock(return_value=0)) as m:
        r = client.post(f"/api/v1/references/{ref.id}/canon/extract-relations")
    assert r.status_code == 202
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && python -m pytest tests/test_canon_router.py::test_graph_endpoint tests/test_canon_router.py::test_extract_relations_requires_entities tests/test_canon_router.py::test_extract_relations_triggers -v`
Expected: FAIL

- [ ] **Step 3: 实现**（加到 `routers/canon.py`；需 `import asyncio`（文件已 import）、`from app.core.database import engine`（已 import）、`from sqlalchemy import func`（在文件 import 行补 `func`））

```python
@router.get("/graph", response_model=CanonGraphOut)
async def get_graph(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    nodes = (await db.execute(select(CanonEntity).where(
        CanonEntity.reference_id == reference_id).order_by(
        CanonEntity.entity_type, CanonEntity.id))).scalars().all()
    edges = (await db.execute(select(CanonRelation).where(
        CanonRelation.reference_id == reference_id).order_by(
        CanonRelation.id))).scalars().all()
    return {"nodes": nodes, "edges": edges}


@router.post("/extract-relations", status_code=202)
async def start_relation_extraction(
    reference_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _get_owned_ref(reference_id, db, user)
    # 须已有实体
    cnt = (await db.execute(select(func.count()).select_from(CanonEntity).where(
        CanonEntity.reference_id == reference_id))).scalar() or 0
    if cnt == 0:
        raise HTTPException(status_code=400, detail="请先提取设定（实体）再抽取关系")
    # 并发守卫：复用 entity job 表，避免与正在进行的提取冲突
    existing = (await db.execute(select(CanonExtractionJob).where(
        CanonExtractionJob.reference_id == reference_id,
        CanonExtractionJob.status.in_(["pending", "processing"]),
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="该原作已有任务进行中")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    asyncio.create_task(extract_relations_for_reference(reference_id, session_factory))
    return {"message": "关系抽取已启动", "reference_id": reference_id}
```

- [ ] **Step 4: 运行确认通过 + canon 全回归**

Run: `cd backend && python -m pytest tests/ -k canon -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/routers/canon.py backend/tests/test_canon_router.py
git commit -m "feat(canon): graph 端点 + extract-relations 触发端点"
```

---

## Phase E — 前端

> 前端无单测基建；验证 = 类型/构建通过 + 部署后人工核对。
> Docker 构建用 `build:docker`（跳过 vue-tsc），但本地 `npm run build` 会因 `noUnusedLocals` 等报错——提交前本地至少跑 `npm run build:docker`。

### Task E1: 安装 relation-graph-vue3 + canon.ts 类型与 API

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/api/canon.ts`

- [ ] **Step 1: 安装依赖**

Run: `cd frontend && npm install relation-graph-vue3 --save`
Expected: `package.json` 的 dependencies 出现 `relation-graph-vue3`

- [ ] **Step 2: 扩展 canon.ts**

把 `CanonEntityType` union 扩为 10：

```ts
export type CanonEntityType =
  | 'character' | 'location' | 'ability' | 'faction' | 'worldrule'
  | 'event' | 'item' | 'race' | 'realm' | 'concept'
```

追加关系类型与接口、API：

```ts
export type CanonRelationReview =
  | 'ai_extracted' | 'user_verified' | 'user_edited' | 'user_added'

export interface CanonRelation {
  id: number
  reference_id: number
  source_entity_id: number
  target_entity_id: number
  relation_type: string
  label: string | null
  summary: string | null
  source_refs: CanonSourceRef[]
  confidence: number
  review_status: CanonRelationReview
  created_at: string
  updated_at: string | null
}

export interface CanonGraph {
  nodes: CanonEntity[]
  edges: CanonRelation[]
}

export interface CanonRelationCreate {
  source_entity_id: number
  target_entity_id: number
  relation_type: string
  label?: string | null
  summary?: string | null
  source_refs?: CanonSourceRef[]
}

export interface CanonRelationUpdate {
  relation_type?: string
  label?: string | null
  summary?: string | null
  review_status?: CanonRelationReview
}
```

在 `canonApi` 对象里追加方法：

```ts
  getGraph(refId: number) {
    return request.get<CanonGraph>(`/references/${refId}/canon/graph`)
  },
  listRelations(refId: number) {
    return request.get<CanonRelation[]>(`/references/${refId}/canon/relations`)
  },
  createRelation(refId: number, data: CanonRelationCreate) {
    return request.post<CanonRelation>(`/references/${refId}/canon/relations`, data)
  },
  updateRelation(refId: number, id: number, data: CanonRelationUpdate) {
    return request.put<CanonRelation>(`/references/${refId}/canon/relations/${id}`, data)
  },
  deleteRelation(refId: number, id: number) {
    return request.delete(`/references/${refId}/canon/relations/${id}`)
  },
  extractRelations(refId: number) {
    return request.post(`/references/${refId}/canon/extract-relations`, undefined, { skipErrorToast: true })
  },
```

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build:docker`
Expected: 构建成功，无类型错误

- [ ] **Step 4: 提交**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/api/canon.ts
git commit -m "feat(canon): 前端关系/图谱 API 与 10 维度类型"
```

### Task E2: CanonGraphView 图谱组件

**Files:**
- Create: `frontend/src/components/canon/CanonGraphView.vue`

- [ ] **Step 1: 创建组件**

```vue
<template>
  <div class="canon-graph">
    <div class="graph-toolbar">
      <el-select v-model="typeFilter" multiple collapse-tags placeholder="按维度筛选"
                 size="small" style="width: 260px">
        <el-option v-for="t in ENTITY_TYPES" :key="t" :label="TYPE_LABEL[t]" :value="t" />
      </el-select>
      <el-button size="small" @click="reload">刷新</el-button>
      <el-text type="info" size="small">{{ nodeCount }} 节点 · {{ edgeCount }} 关系</el-text>
    </div>
    <el-empty v-if="!loading && edgeCount === 0 && nodeCount === 0"
              description="尚无图谱，请先在列表视图提取设定" />
    <RelationGraph v-else ref="graphRef" :options="graphOptions"
                   @node-click="onNodeClick" @line-click="onLineClick" />
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import RelationGraph from 'relation-graph-vue3'
import { canonApi, type CanonEntityType, type CanonGraph } from '@/api/canon'

const props = defineProps<{ referenceId: number }>()
const emit = defineEmits<{ (e: 'select-node', id: number): void
                           (e: 'select-edge', id: number): void }>()

const ENTITY_TYPES: CanonEntityType[] = ['character','location','ability','faction',
  'worldrule','event','item','race','realm','concept']
const TYPE_LABEL: Record<CanonEntityType, string> = {
  character:'角色', location:'地点', ability:'能力', faction:'势力', worldrule:'世界观规则',
  event:'事件', item:'物品', race:'种族血脉', realm:'境界体系', concept:'专有术语' }
const TYPE_COLOR: Record<CanonEntityType, string> = {
  character:'#5B8FF9', location:'#5AD8A6', ability:'#F6BD16', faction:'#E8684A',
  worldrule:'#9270CA', event:'#FF9D4D', item:'#269A99', race:'#FF99C3',
  realm:'#6DC8EC', concept:'#A6A6A6' }

const graphRef = ref()
const loading = ref(false)
const raw = ref<CanonGraph>({ nodes: [], edges: [] })
const typeFilter = ref<CanonEntityType[]>([])
const graphOptions = reactive({ defaultLineShape: 1, defaultJunctionPoint: 'border',
  defaultNodeShape: 0, layouts: [{ layoutName: 'force' }] })

const nodeCount = computed(() => visibleNodes().length)
const edgeCount = computed(() => raw.value.edges.length)

function visibleNodes() {
  if (typeFilter.value.length === 0) return raw.value.nodes
  return raw.value.nodes.filter(n => typeFilter.value.includes(n.entity_type))
}

function buildGraphJson() {
  const visIds = new Set(visibleNodes().map(n => n.id))
  const nodes = visibleNodes().map(n => ({
    id: String(n.id), text: n.canonical_name, color: TYPE_COLOR[n.entity_type],
    nodeShape: 0,
    width: n.importance === 'critical' ? 70 : n.importance === 'major' ? 56 : 44,
  }))
  const lines = raw.value.edges
    .filter(e => visIds.has(e.source_entity_id) && visIds.has(e.target_entity_id))
    .map(e => ({ from: String(e.source_entity_id), to: String(e.target_entity_id),
                 text: e.label || e.relation_type, _rid: e.id }))
  return { rootId: nodes[0]?.id, nodes, lines }
}

async function render() {
  const inst = graphRef.value?.getInstance?.()
  if (inst) await inst.setJsonData(buildGraphJson())
}

async function reload() {
  loading.value = true
  try {
    const { data } = await canonApi.getGraph(props.referenceId)
    raw.value = data
    await render()
  } finally { loading.value = false }
}

function onNodeClick(node: any) { emit('select-node', Number(node.id)); return false }
function onLineClick(line: any, link: any) {
  const rid = link?.relations?.[0]?._rid ?? line?._rid
  if (rid != null) emit('select-edge', Number(rid)); return false
}

watch(typeFilter, render)
onMounted(reload)
defineExpose({ reload })
</script>

<style scoped>
.canon-graph { display: flex; flex-direction: column; height: 70vh; }
.graph-toolbar { display: flex; gap: 12px; align-items: center; padding: 8px 0; }
.canon-graph :deep(.rel-map) { flex: 1; min-height: 0; }
</style>
```

> 注：`relation-graph-vue3` 的精确 API（`getInstance/setJsonData`、`@node-click`/`@line-click`、options 字段）以安装后 `node_modules/relation-graph-vue3` 的 README/types 为准；若签名不同按其文档微调，语义不变（节点=实体、线=关系、点击发 select 事件）。

- [ ] **Step 2: 构建验证**

Run: `cd frontend && npm run build:docker`
Expected: 构建成功

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/canon/CanonGraphView.vue
git commit -m "feat(canon): CanonGraphView 知识图谱可视化组件"
```

### Task E3: ReferenceCanonView 加 Tab + 详情侧栏

**Files:**
- Modify: `frontend/src/views/ReferenceCanonView.vue`

- [ ] **Step 1: 扩展维度标签/配色**

在 `<script setup>` 中把 `entityTypeLabel` 覆盖 10 类（与组件一致）：character 角色 / location 地点 / ability 能力 / faction 势力 / worldrule 世界观规则 / event 事件 / item 物品 / race 种族血脉 / realm 境界体系 / concept 专有术语。`groupedEntities` 的分组顺序同步用 10 类数组。

- [ ] **Step 2: 加 Tab 包裹**

把现有「实体分组列表」整体包进 `el-tabs` 的第一个 `el-tab-pane`（label「列表视图」），新增第二个 `el-tab-pane`（label「图谱视图」）渲染：

```vue
<el-tabs v-model="activeTab">
  <el-tab-pane label="列表视图" name="list">
    <!-- 现有 entity-groups / 空状态 / 骨架，原样保留 -->
  </el-tab-pane>
  <el-tab-pane label="图谱视图" name="graph">
    <div class="graph-actions">
      <el-button size="small" :loading="extractingRel" @click="handleExtractRelations">
        {{ extractingRel ? '抽取关系中…' : '抽取关系' }}
      </el-button>
    </div>
    <CanonGraphView v-if="activeTab === 'graph'" ref="graphViewRef"
      :reference-id="referenceId"
      @select-node="onSelectNode" @select-edge="onSelectEdge" />
  </el-tab-pane>
</el-tabs>

<el-drawer v-model="detailVisible" :title="detailTitle" size="360px">
  <!-- 节点：summary/aliases/source_refs；边：label/relation_type/source_refs + 编辑/删除/标记已核对 -->
</el-drawer>
```

`<script setup>` 追加：

```ts
import CanonGraphView from '@/components/canon/CanonGraphView.vue'
const activeTab = ref<'list' | 'graph'>('list')
const extractingRel = ref(false)
const graphViewRef = ref()
const detailVisible = ref(false)
const detailTitle = ref('')

async function handleExtractRelations() {
  extractingRel.value = true
  try {
    await canonApi.extractRelations(referenceId)
    // 复用现有 SSE 订阅监听 relation_progress / done；done 后刷新图谱
  } catch (e: any) {
    if (e?.response?.status !== 409) ElMessage.error('关系抽取启动失败')
  } finally { extractingRel.value = false }
}
function onSelectNode(id: number) { /* 取实体详情填 drawer */ detailVisible.value = true }
function onSelectEdge(id: number) { /* 取关系详情填 drawer */ detailVisible.value = true }
```

> SSE：现有 `ReferenceCanonView` 已订阅 canon stream。扩展其 `onmessage` 处理：遇 `relation_progress` 更新进度文案；遇 `done` 且 `activeTab==='graph'` 时调用 `graphViewRef.value?.reload()`。

- [ ] **Step 3: 构建验证**

Run: `cd frontend && npm run build:docker`
Expected: 构建成功

- [ ] **Step 4: 提交**

```bash
git add frontend/src/views/ReferenceCanonView.vue
git commit -m "feat(canon): 设定校对页加图谱视图 Tab 与详情侧栏"
```

---

## Phase F — 集成验证与部署

### Task F1: 后端全回归

- [ ] **Step 1:** Run: `cd backend && python -m pytest tests/ -k canon -v` — Expected: 全 PASS
- [ ] **Step 2:** Run: `cd backend && python -m pytest tests/ -q` — Expected: 全量回归无新失败

### Task F2: 部署与端到端人工核对

- [ ] **Step 1: 重建后端 + 前端**

```bash
cd /data/projects/novel-writer
docker compose build backend frontend && docker compose up -d backend frontend
```

> 后端重启时 `Base.metadata.create_all` 自动建 `canon_relations` 表（无需手工迁移）。验证：
> `docker exec novel-writer-db-1 psql -U <user> -d <db> -c "\d canon_relations"`

- [ ] **Step 2: 端到端核对**
  - 上传/选择一部原作 → 「提取设定」→ 进度走完，列表视图出现 10 维度实体。
  - 切「图谱视图」→ 看到节点-边图；点节点高亮+侧栏详情；点边看关系+溯源。
  - 「抽取关系」可单独重跑；手动新增/编辑/删除关系生效。
  - 验证前端产物含新代码：`docker exec novel-writer-frontend grep -rl CanonGraphView /usr/share/nginx/html/assets`

### Task F3: 合并

- [ ] **Step 1:** 自检 + 让 reviewer/verifier 过一遍后，按项目惯例把 `feat/canon-knowledge-graph` 合并回 `main`（参考历史 `Merge feat/canon-extraction`）。

---

## Self-Review 记录

- **Spec 覆盖：** 维度 6→10（A1/A2/E1/E3）✓；CanonRelation 表（B1）✓；关系受控词表+兜底（C1）✓；RELATION_EXTRACT 阶段（C3/C4）✓；6 端点 relations CRUD+graph+extract-relations（D1/D2）✓；图谱视图 relation-graph-vue3（E2/E3）✓；无 Alembic 迁移注意（F2）✓；测试（各 Task）✓；二创关系注入=非目标（spec §7/§10，本计划不含，符合）✓。
- **类型一致：** `extract_relations_for_reference`（C3 定义，C4/D2 调用一致）；`_build_name_index`/`_resolve_relations`（C2 定义，C3 调用一致）；`RELATION_TYPES_CN`/`build_relation_prompt`（C1 定义，C3 调用一致）；`CanonGraphOut{nodes,edges}`（B2 定义，D2 返回、E1 `CanonGraph` 对应一致）。
- **占位符：** 无 TBD/TODO；前端 relation-graph-vue3 具体 API 以安装后类型为准（已显式标注为按文档微调，非占位）。
