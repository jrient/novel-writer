# 原作知识图谱（Canon Knowledge Graph）设计文档

- 日期：2026-06-05
- 状态：已通过 brainstorming 确认，待实现计划
- 作者：Claude（与用户 brainstorming 共识）

## 1. 背景与目标

novel-writer 的「二创」链路已具备：上传/选择原作小说（`ReferenceNovel`）→ 触发设定提取（`run_canon_extraction`：CHUNK→ATOMIC_EXTRACT→MERGE→PERSIST）→ 提取 6 维度实体（`CanonEntity`）→ 在 `ReferenceCanonView.vue`「原作设定校对」页分组列表检阅 → `canon_context` 注入二创创作。

**问题：** 现有 canon 是按类型分组的**扁平实体清单**，不是真正的「知识图谱」——缺少实体之间的结构化**关系边**，检阅也只是卡片列表而非可交互的节点-边图谱。

**目标：** 在不破坏现有 canon 的前提下，将其**升级为真·知识图谱**：
1. 扩展实体维度 6 → 10。
2. 新增一等公民的**关系边**抽取与存储（三元组 `<头实体, 关系, 尾实体>`）。
3. 在检阅页新增**图谱视图**（交互式力导向图），与现有列表视图并存。

**调研依据（叙事/文学知识图谱最佳实践）：**
- 知识图谱 = 三元组 `<head, relation, tail>`，节点是实体、边是关系。
- 实体维度随题材而变（如《沙丘》用到 9 类，含 FACTION/RITUAL/PROPHECY）；现有 6 维度是扎实基底。
- 文学关系是**开放域**、难穷举，最佳实践为**受控关系词表 + 自由文本兜底**。
- 来源：GOLEM Ontology for Narrative and Fiction (MDPI 2025)；Relation Clustering in Narrative Knowledge Graphs (arXiv 2011.13647)；网文 NER+关系抽取实践。

## 2. 维度（节点类型）：6 → 10

`ENTITY_TYPES`（`canon_pipeline.py`）由 6 扩为 10：

| key | 中文 | 状态 | 说明 |
|-----|------|------|------|
| character | 角色 | 现有 | |
| location | 地点 | 现有 | |
| ability | 能力 | 现有 | 功法/技能/异能 |
| faction | 势力 | 现有 | 门派/组织/国家 |
| worldrule | 世界观规则 | 现有 | 体系/法则 |
| event | 事件 | 现有 | |
| **item** | 物品 | 新增 | 法宝/神器/丹药/功法秘籍 |
| **race** | 种族/血脉 | 新增 | 人族/妖族/血脉传承 |
| **realm** | 境界/体系 | 新增 | 修为境界/等级体系 |
| **concept** | 专有术语 | 新增 | 设定专名（非上述具体物） |

同步改动点：`canon_pipeline.ENTITY_TYPES`、`canon_prompts`（atomic/merge prompt 的类型枚举与示例）、`canon_context._TYPE_CN`、前端 `canon.ts` 类型标签与颜色映射、`ReferenceCanonView` 的 `entityTypeLabel`。

## 3. 关系边（Relation）：本设计核心

### 3.1 受控关系词表（按「头类型 → 尾类型」组织）

| 头 → 尾 | 关系类型（relation_type） |
|---------|--------------------------|
| 角色 ↔ 角色 | 亲属 / 师徒 / 情感 / 盟友 / 敌对 / 上下级 |
| 角色 → 势力 | 属于 / 领导 / 创立 / 敌对 |
| 角色 → 地点 | 出身 / 居于 / 统治 |
| 角色 → 能力 | 掌握 |
| 角色 → 物品 | 持有 / 炼制 |
| 角色 → 种族 | 属于种族 |
| 角色 → 境界 | 处于境界 |
| 角色 → 事件 | 参与 / 主导 / 受害 |
| 物品 → 能力 | 承载 / 记载 |
| 种族 → 能力 | 天赋 |
| 境界 ↔ 境界 | 进阶 |
| 事件 ↔ 事件 | 因果 / 时序 / 伏笔 |
| 事件 → 地点 | 发生于 |
| 势力 ↔ 势力 | 结盟 / 敌对 / 隶属 |
| 地点 → 地点 | 隶属 |

**兜底：** 不匹配受控词表时，用自由文本 `label` 表达关系（`relation_type="custom"`）。

### 3.2 数据模型（新增 `CanonRelation`，挂 `canon.py`）

```python
class CanonRelation(Base):
    __tablename__ = "canon_relations"
    id: int (pk)
    reference_id: int (FK reference_novels.id, CASCADE, index)
    source_entity_id: int (FK canon_entities.id, CASCADE, index)
    target_entity_id: int (FK canon_entities.id, CASCADE, index)
    relation_type: str(40)   # 受控词表 key 或 "custom"
    label: str(100) | None   # 显示文案；custom 时为自由文本
    summary: str/Text | None # 关系说明（可选）
    source_refs: JSON (list) # 溯源 [{"chapter": "片段N", "quote": "≤40字"}]
    confidence: float = 1.0
    # ai_extracted / user_verified / user_edited / user_added
    review_status: str(20) = "ai_extracted"
    created_at / updated_at
```

去重键：`(reference_id, source_entity_id, target_entity_id, relation_type)`。

**迁移注意（项目无 Alembic，靠 `Base.metadata.create_all`）：**
- `canon_relations` 是**新表**，应用重启即由 `create_all` 自动创建，无需手工迁移。
- **不给 `CanonExtractionJob` 加列**（create_all 不会 ALTER 已存在表）。关系阶段进度仅通过 SSE 事件推送，关系总数由 `count(canon_relations)` 实时查询得出，避免对既有表做迁移。

## 4. 抽取层：新增 `RELATION_EXTRACT` 阶段

在现有 `run_canon_extraction` 的 PERSIST（实体落库）之后追加阶段：

```
... → MERGE_DISAMBIGUATE → PERSIST(entities)
    → RELATION_EXTRACT → PERSIST(relations) → done
```

- 输入：已归并去重的实体清单（id + canonical_name + entity_type + aliases）+ 原文分块（复用第一阶段的 chunks）。
- 对每个 chunk 并行（沿用 `ATOMIC_CONCURRENCY`）调用 LLM，传入「本文档实体清单」，要求只在清单内实体间抽三元组，输出 `[{source, target, relation_type, label, quote}]`；`source/target` 用 canonical_name 回链到 entity_id（找不到则丢弃）。
- 归并去重后落 `CanonRelation`，`review_status="ai_extracted"`。
- 进度：复用 `canon_event_bus`，新增 SSE phase 标识 `relation_extract`（payload 带 phase/done/total）。前端进度条文案增加「关系抽取中…」。
- 新增 prompt 构造函数 `build_relation_prompt(entities, chunk_text)`（`canon_prompts.py`），关系类型枚举取自 §3.1 受控词表 + custom。
- 容错沿用现有 `_safe_json_array`、`return_exceptions=True`。

**重跑策略：** 关系抽取为独立阶段，可在实体已存在时单独重跑（端点 `POST /extract-relations`，见 §5）。重跑前清空该 reference 既有 `ai_extracted` 关系，保留 `user_*` 关系。

## 5. API 层（`routers/canon.py`，前缀 `/api/v1/references/{reference_id}/canon`）

新增：
- `GET /relations` → list[CanonRelationOut]（可按 relation_type / 端点 entity_id 过滤）
- `POST /relations` → 手工新增（review_status="user_added"）
- `PUT /relations/{id}` → 编辑（review_status→user_edited；或 verify→user_verified）
- `DELETE /relations/{id}`
- `POST /extract-relations`（202）→ 仅跑关系抽取阶段（实体须已存在，否则 409/400）
- `GET /graph` → 一次性返回 `{nodes: CanonEntityOut[], edges: CanonRelationOut[]}`，供图谱视图直接渲染（避免前端两次请求自行 join）。

Schema（`schemas/canon.py`）新增：`CanonRelationOut / CanonRelationCreate / CanonRelationUpdate / CanonGraphOut`。

## 6. 检阅层（前端）

### 6.1 视图结构
`ReferenceCanonView.vue` 顶部加 `el-tabs`（或分段控件）：
- **列表视图**：现有实体分组卡片列表，**保持不变**。
- **图谱视图**（新）：调 `GET /canon/graph`，用 `relation-graph-vue3` 渲染节点-边力导向图。

### 6.2 图谱视图（新组件 `components/canon/CanonGraphView.vue`）
- 库：`relation-graph-vue3`（前端现无任何图库，新引入；专为 Vue3 关系图设计，集成最快，支持节点/边自定义与点击事件）。
- 节点：按 `entity_type` 着色（10 色板），按 `importance`（critical/major/minor）定大小，文案 = canonical_name。
- 边：显示 relation_type 文案；不同关系类型可不同颜色/样式（如敌对=红、亲属/师徒=暖色）。
- 交互：
  - 点节点 → 高亮其邻接节点与边，侧栏显示实体详情（summary/aliases/source_refs）。
  - 点边 → 侧栏显示关系详情 + 溯源原文，可编辑/删除/标记已核对。
  - 工具栏：按维度过滤节点、按关系类型过滤边、布局切换（力导向/中心展开）、重置。
  - 「手动新增关系」：选两个节点 + 选关系类型/填自由文本 → POST /relations。
- 空状态：实体存在但无关系时，提示「点击『抽取关系』生成图谱」，按钮触发 `POST /extract-relations`，SSE 显示进度。

### 6.3 前端 API（`api/canon.ts`）
新增 `RelationType` 枚举、`CanonRelation` 接口、`CanonGraph` 接口，及 `relationsApi`（list/create/update/delete/extractRelations/getGraph）。

## 7. 二创接入（本期可选，后续增强）
`canon_context.build_canon_context` 可选拼接关键关系（按 importance 排序的实体之间的边），形成「X 是 Y 的师父」「A 势力与 B 势力敌对」等事实约束注入二创 prompt。**本期先保证图谱建立与检阅，关系注入作为 follow-up。**

## 8. 测试
- 后端：仿 `tests/test_canon_prompts.py`，加 `test_relation_prompt`（prompt 含受控词表/实体清单）、关系抽取的 JSON 解析与 entity 回链单测、relations CRUD 路由测试、graph 端点测试、重跑保留 user_* 关系的测试。
- 前端：图谱组件渲染 nodes/edges 的基本快照/挂载测试（如项目有前端测试基建；当前 Dockerfile 用 `build:docker` 跳过 vue-tsc，注意未用变量等 TS 报错不阻断 docker 构建但本地 `npm run build` 会报）。

## 9. 影响文件清单
**后端：** `models/canon.py`(+CanonRelation)、`schemas/canon.py`(+4 schema)、`routers/canon.py`(+5 端点)、`services/canon_pipeline.py`(ENTITY_TYPES 扩 10 + RELATION_EXTRACT 阶段 + 关系归并落库)、`services/canon_prompts.py`(类型枚举扩 10 + build_relation_prompt)、`services/canon_event_bus.py`(关系阶段 SSE，复用)、`services/canon_context.py`(_TYPE_CN 扩 10 + 可选关系注入)、`main.py`(确保 import 新模型以纳入 metadata)。
**前端：** `api/canon.ts`、`views/ReferenceCanonView.vue`(加 Tab)、`components/canon/CanonGraphView.vue`(新)、`package.json`(+relation-graph-vue3)。
**部署：** 后端重启即建 `canon_relations` 表；前端改动需 `docker compose build frontend && docker compose up -d frontend`（前端非热更新）。

## 10. 非目标（YAGNI）
- 不引入图数据库（继续用 PostgreSQL 关系表存边，规模足够）。
- 不做跨原作的全局图谱合并。
- 不做关系的时间演化/版本快照。
- 本期不做二创 prompt 的关系注入（留作 follow-up）。
