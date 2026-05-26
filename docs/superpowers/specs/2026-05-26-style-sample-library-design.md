# Spec-1：知乎严选风格样本库 设计文档

- 日期：2026-05-26
- 状态：待 user 评审
- 关联后续：Spec-2「剧本 → 知乎严选风格短篇小说」主工作流（依赖本 spec 已交付）

---

## 一、目标与范围

### 目标
建立一个独立、运营维护、全局共享的「知乎严选风格样本库」，作为下游 Spec-2 生成 pipeline 的：

1. **few-shot 节选源**（`prose_excerpt`）
2. **风格指南 prompt 片段源**（`prompt_fragment`）
3. **按情境检索相似桥段的语义索引**（chunk-level embedding）

### 范围内
- 上传知乎严选风格短篇（txt / md / docx）
- 全文向量索引，支持语义检索（query → Top-K 相似桥段/全篇）
- 上传时一次性 LLM 抽取「风格指南片段」，结果落库复用
- 列表 / 详情 / 删除 / 重抽取 / 检索 五个 API
- 前端独立「风格样本库」页面（上传 + 列表 + 详情）

### 范围外
- 手动打分 / 评级
- 复杂权限模型（多角色细分）
- 抽取结果的人工微调界面（发现质量差直接 reindex，不在前端改）
- 多语言 / 跨流派支持

### 与已有 `ReferenceNovel` 的边界
- `ReferenceNovel` 是用户上传的个人参考小说，用规则统计文风特征 —— **保留不动**
- `StyleSample` 是运营资产，全局共享，用 LLM 抽取风格指南 —— **新建独立表**
- 复用底层 `embedding_service` 和 `file_parser`，但实体表 / 路由 / 前端页面完全分开，避免语义混淆

---

## 二、模块分解与边界

| 单元 | 类型 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `models/style_sample.py` | ORM 实体 | — | `StyleSample`, `StyleSampleChunk` 两张表 | `Base`, `pgvector` |
| `services/style_sample_indexer.py` | 服务 | 文本 + sample_id | 切 chunk → 调 embedding → 写 `StyleSampleChunk` | `embedding_service`, `file_parser` |
| `services/style_guide_extractor.py` | 服务 | 全文 + 元数据 | 结构化 + 自由文本两种「风格指南片段」，写回 `StyleSample.style_guide` | `ai_service` |
| `routers/style_sample.py` | API | HTTP | CRUD + 检索 + 重抽取 5 个端点 | 上面 2 个 service |
| `frontend/views/StyleSampleLibrary.vue` | 页面 | 用户操作 | 上传 / 列表 / 详情 3 个面板 | 新 API |

### 关键设计选择：粒度策略
- **风格指南 = sample-level**（整篇一份）：风格是整体性属性，抽取一次落库即可，0 重复成本
- **embedding = chunk-level**（每段一向量）：用于检索"按情境匹配相似桥段"，下游 Spec-2 用得到
- 两者并用，各管一边，互不混淆

---

## 三、数据模型

```python
# models/style_sample.py

class StyleSample(Base):
    __tablename__ = "style_samples"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 基本信息（运营手动填写，无 owner_id —— 全局共享）
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100))
    source: Mapped[Optional[str]] = mapped_column(String(200))  # "知乎严选"/"盐选"/具体专栏
    genre: Mapped[Optional[str]] = mapped_column(String(50))    # 题材：都市/言情/悬疑/…
    tags: Mapped[Optional[str]] = mapped_column(Text)            # JSON 数组
    notes: Mapped[Optional[str]] = mapped_column(Text)           # 运营备注

    # 文件
    file_path: Mapped[Optional[str]] = mapped_column(String(500))
    file_format: Mapped[Optional[str]] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text, nullable=False)   # 全文（短篇直接存库）
    total_chars: Mapped[int] = mapped_column(Integer, default=0)

    # 抽取产物（JSON 落库，可重抽取覆盖）
    style_guide: Mapped[Optional[str]] = mapped_column(Text)
    extraction_model: Mapped[Optional[str]] = mapped_column(String(100))
    extracted_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 索引状态
    index_status: Mapped[str] = mapped_column(String(20), default="pending")
        # pending / indexing / ready / failed
    index_error: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())


class StyleSampleChunk(Base):
    __tablename__ = "style_sample_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    sample_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("style_samples.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

### `style_guide` 的 JSON Schema

```json
{
  "structured": {
    "pov": "第一人称 / 第三人称",
    "tense": "过去时 / 现在时",
    "sentence_length": "短句为主 / 长短交错 / …",
    "dialogue_density": "high / medium / low",
    "pacing": "强反转密集 / 缓推 / …",
    "opening_formula": "倒叙抛悬念 / 直接对话切入 / …",
    "ending_formula": "高甜余韵 / 反转收束 / …",
    "signature_devices": ["内心独白", "短段落分隔", "..."]
  },
  "prose_excerpt": "<200 字左右的典型段落原文，作为 few-shot 节选>",
  "prompt_fragment": "<可直接拼进 system prompt 的自由文本指南，约 300 字>"
}
```

### 关键决定
- 新建 `StyleSampleChunk`，**不**复用 `NovelChunk`：后者绑定 `reference_id`，混用要加 `source_type` 字段污染现有查询；独立表 + FK + CASCADE 更干净
- `style_guide` 落 JSON Text 而非拆 N 列：schema 还在演进，JSON 抗变更
- 无 `owner_id`：全局共享、运营资产
- `index_status` 显式建模"已上传但 embedding 没跑完"的中间态，避免下游 Spec-2 拿到半成品

---

## 四、API 设计

挂在 `/api/v1/style-samples`，6 个端点：

```
POST   /api/v1/style-samples              上传新样本
       multipart: file + title + (author, source, genre, tags, notes)
       行为: 同步创建行(index_status=pending) + 后台任务跑 chunk+embedding+抽取
       返回: sample_id;前端轮询 GET 直到 index_status=ready

GET    /api/v1/style-samples              列表(分页 + 按 genre/tags filter)
       不返回 content / chunks,只返回元信息和 index_status

GET    /api/v1/style-samples/{id}         详情
       返回 sample 全部字段 + 解析后的 style_guide,不返回 chunks(太重)

DELETE /api/v1/style-samples/{id}         删除(CASCADE 删 chunks)

POST   /api/v1/style-samples/{id}/reindex 重跑 embedding + 重抽 style_guide
       用于 prompt 调优后重抽,或 embedding 模型升级后重建

POST   /api/v1/style-samples/search       语义检索
       body: {"query": "高甜结尾",
              "top_k": 5,
              "filter": {"genre": "都市言情", "tags": [...]}}
       返回: [{sample, top_chunks: [{content, char_count, similarity}],
               style_guide: {prompt_fragment, prose_excerpt}}]
```

### 关键设计选择

1. **上传走"同步创建 + 异步索引"**：上传立即返回 sample_id，embedding 和 LLM 抽取在 FastAPI background task 跑。前端轮询 `GET /{id}` 看 `index_status`。
   - 优于全同步：单篇 8k–2w 字，embedding 切几十 chunk + LLM 抽取要 30s–2min，HTTP 挂太久
   - 优于异步 + SSE：MVP 阶段轮询足够，不引入 `adaptation_event_bus` 复杂度

2. **`/search` 一并返回 `prompt_fragment` 与 `prose_excerpt`**：Spec-2 的 pipeline 调一次 search 拿全所需，少一次往返

3. **认证**：全部端点要求 `get_current_user`（即 `routers/auth.py` 现有的登录态依赖），**不做 owner 限制**——任意登录用户能读、能上传、能删除、能重抽取。理由：本期样本库是运营内部使用的资产，使用者都是受信任的内部账号；细分 admin 角色推到 Spec-3 视需求再加。前端通过隐藏入口/UI 做软限制（仅在管理员菜单暴露上传/删除）

---

## 五、风格指南抽取 prompt 设计

`style_guide_extractor` 是质量关键。输入是全文（8k–2w 字），输出 JSON 的三段。

### 抽取 prompt

```
[System]
你是一位资深风格分析师，专门分析中文短篇网文的写作风格。
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

[User]
《{title}》全文：
{content}
```

### 关键决定

1. **`prompt_fragment` 严格剥离具体情节**：Spec-2 拿这段拼 prompt 时，需要的是"知乎严选怎么写"，不是"这一篇写了什么"。若不剥离，会污染下游生成出来的剧情
2. **`prose_excerpt` 原文照抄**：作为 few-shot 节选，下游可选择"塞 fragment + 塞 excerpt"双重锚
3. **抽取模型用 backend 默认 LLM**（`ai_service`，当前 `.env` 配置的 Claude Sonnet 4 或 GPT-4o）；不在 Spec-1 硬编码；`extraction_model` 字段记录用于以后比较
4. **失败处理**：单次抽取失败 → `index_status=failed` + `index_error` 记原因，用户可手动 reindex；MVP 不做自动 backoff 重试
5. **不强制 JSON schema 校验**：LLM JSON 解析失败 → 直接标 failed；不引入 instructor / pydantic-ai

---

## 六、Chunk 切分与 embedding 策略

### 切分规则
- 优先按"自然段落"切（中文 `\n\n` 或单 `\n`）
- 每个 chunk 目标 300–500 字
  - 超 500 字 → 在 500 字位置往前找最近的中文句末符（`。`/`！`/`？`/`…`）作为切点；若 400 字内找不到才退化为硬切到 500
  - 少于 100 字 → 与下一段合并；若没有下一段（已是最后一段），允许独立成 chunk
- **不重叠**（无 overlap）：overlap 主要服务长上下文 RAG，对"风格相似桥段检索"用处不大且 token 浪费
- 单篇 8k–2w 字预期产 20–60 个 chunk

### embedding 策略
- 复用 `embedding_service.generate_embeddings(List[str])`，批量调用（一次最多 50 条）
- 模型走 `EMBEDDING_MODEL` 配置（当前 1536 维，与 `Vector(1536)` 列匹配；与现有 `NovelChunk.embedding` 维度一致）
- 失败处理：整篇任一 batch 失败 → `index_status=failed`，chunks 全删；MVP 不做部分成功

### 检索查询
- 接 `pgvector` 余弦相似度 `embedding <=> query_embedding`
- `top_k` 默认 5，硬上限 20
- 同一 sample 多 chunk 命中 → service 层聚合，按 sample 折叠，返回每个 sample 的最高分 chunk + 该 sample 全部命中 chunks 列表
- `filter.genre` / `filter.tags` 在 SQL where 里做（join `style_samples`）

### 关键决定
- 无 overlap、按段切：保持简单，质量够用，避免 chunk 间冗余污染
- "按 sample 折叠"返回：下游 Spec-2 想要的是"找 5 个相似风格的样本"，而非"5 个相似段落"——若只按 chunk 排序，5 个 hit 可能来自同 2 篇，损失多样性

---

## 七、前端页面

新增 `views/StyleSampleLibrary.vue`，路由 `/style-samples`，主导航加一个入口。

**遵守 [[feedback_no_split_layout]]**：全程上下堆叠 + 抽屉/弹窗，**不做"左列表右详情"分屏**。

### 页面结构

```
┌─ 顶部工具栏 ────────────────────────────────┐
│  [+ 上传样本]  [刷新]  搜索框 [_____] 题材[v] │
└────────────────────────────────────────────┘
┌─ 列表区 ────────────────────────────────────┐
│  表格列：标题 / 作者 / 来源 / 题材 / 字数 /  │
│         索引状态徽章 / 抽取时间 / 操作       │
│  操作：[详情] [重抽取] [删除]                │
│  状态徽章：pending(灰) / indexing(蓝)        │
│           / ready(绿) / failed(红 tooltip)   │
└────────────────────────────────────────────┘

[+ 上传样本] → 抽屉/弹窗（不分屏）：
  - 文件上传（txt/md/docx，单个）
  - 元数据表单：标题（必填）、作者、来源、题材（下拉）、tags、备注
  - 提交后关闭抽屉，列表自动刷新；新行 status=indexing
  - 列表每 5s 轮询一次，直到所有非 ready 行变 ready/failed

[详情] → 弹窗（不分屏）：
  - 元数据
  - 抽取产物 3 段：
      structured（键值表）
      prose_excerpt（灰底引用块）
      prompt_fragment（可复制按钮）
  - 全文（折叠，默认收起）
  - chunk 列表（折叠，显示前 5 条 + "共 N 段"）
```

### 关键设计
- 全程上下堆叠 + 抽屉/弹窗
- 详情默认折叠全文 / chunks，避免一次渲染几万字
- 轮询而非 SSE / WebSocket：MVP 简单可靠
- 不做"前端微调 prompt_fragment 后保存"——发现质量差直接 reindex

---

## 八、错误处理 / 测试 / 出口标志

### 错误处理

| 场景 | 行为 |
|---|---|
| 上传文件解析失败 | API 同步 400，不创建 sample 行 |
| embedding 任一 batch 失败 | `index_status=failed`，写 `index_error`，chunks 全删，sample 行保留 |
| LLM 抽取失败 / JSON 解析失败 | 同上，`index_error` 记原因 |
| 抽取部分成功（embedding ✓ 但 guide ✗，或反之） | 也标 failed，整体重做（MVP 不分阶段重试） |
| 用户对 failed 行点"重抽取" | 清空 chunks / guide，重置 `status=indexing`，重跑全流程 |
| 检索 query 为空 | 400 |
| 检索结果命中 0 条 | 返回空列表，不报错 |

### 测试策略

**Unit 测试**（`backend/tests/`）：
- `test_style_sample_indexer.py`：mock embedding service，验证 chunk 切分规则（按段、字数边界、合并/硬切）
- `test_style_guide_extractor.py`：mock LLM，验证 JSON 解析 + 失败标记
- `test_style_sample_router.py`：FastAPI TestClient，覆盖 5 个端点的 happy path + 主要 error path

**集成测试**：1 个端到端 happy path —— 上传真实小样本 → 轮询到 ready → 检索 → 拿到 guide。用 1–2 篇短样本（≤2000 字）走真实 embedding + LLM，关在 `@pytest.mark.integration` 后面，CI 默认跳过。

**手工验收**（spec 完成后做）：
- 上传 3–5 篇真实知乎严选样本
- 看抽出的 `prompt_fragment` 是否符合"剥离情节、只描述写法"的要求
- 检索 "高甜结尾"、"反转" 等典型 query 是否返回合理 hit

### Spec-1 完成 Exit 标志
- 6 个 API 端点全部可用且有单元测试
- 前端列表 / 上传 / 详情 3 个面板可用
- 至少 3 篇真实样本入库、`status=ready`、`prompt_fragment` 人工通读觉得"能直接拼 prompt"
- DB migration 已生成
- Spec-2 可以直接调 `/api/v1/style-samples/search` 拿数据

---

## 九、与现有基础设施的复用关系

| 现有组件 | 用法 | 改动 |
|---|---|---|
| `services/embedding.py` | 直接调 `embedding_service.generate_embeddings()` | 无 |
| `services/file_parser.py` | 直接调 `FileParser.parse_txt/markdown/docx` | 无 |
| `services/ai_service.py` | 抽取 prompt 走默认 LLM provider | 无 |
| `core/database.py` + `Base` | 新表注册 | 仅 import |
| Alembic / 启动期 `Base.metadata.create_all` | 新表 migration 走现有机制 | 仅生成 migration |
| `routers/auth.py` `get_current_user` | 鉴权 | 仅 import |
| `models/reference.py` `ReferenceNovel` | **不复用，不修改** | 无 |
| `models/embedding.py` `NovelChunk` | **不复用** | 无 |

---

## 十、Spec-2 的接口约定（前瞻）

Spec-2 主工作流将通过以下方式消费本库：

```python
# 在 Spec-2 的 pipeline 服务中
hits = await POST("/api/v1/style-samples/search", {
    "query": user_story_premise,   # 用户填的"一句话故事译点"
    "top_k": 3,
    "filter": {"genre": script.genre}
})

system_prompt = STYLE_GUIDE_HEADER + "\n\n".join(
    h["style_guide"]["prompt_fragment"] for h in hits
)
fewshot_examples = [h["style_guide"]["prose_excerpt"] for h in hits]
```

Spec-1 必须保证 `/search` 接口稳定，schema 不破坏性变更。
