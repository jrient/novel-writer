# 原作设定提取子系统 设计文档

- **日期**: 2026-06-03
- **状态**: 已确认，待实施计划
- **路线**: B（分块提取 + 分层聚合 + 实体权威库 + 溯源）
- **范围定位**: 二创小说创作的「地基」——把原作准确提取为可复用、可校对的设定圣经(canon)，供 wizard 二创创作锚定

## 1. 背景与动机

### 1.1 产品愿景
做二创（同人）小说创作：AI 在原作既有知识框架上推演，而非凭空空想。完整链路四阶段：
1. 读原作 → 提取人物/地名/事件/能力/世界观
2. 研究二创笔法/脑洞，与原作融合
3. 问答/对话确定主线大纲（如「穿越乌鸡国国王如何活下去/成仙成佛」）
4. 细化切割集数

### 1.2 形态决策
**增强现有 `wizard`**，而非新建模块或独立站点。现有平台已具备四阶段的大部分「零件」，本子系统补齐最关键的缺口。

### 1.3 现状缺口（为什么「设定提取准确度」是地基）
- **原作上传后无 AI 结构化提取**：`reference.py::_analyze_text` 纯启发式统计（字数/章节/猜类型/文风描述）。`ai_service` 虽有 `extract_characters` prompt，但只抽角色、且写入用户项目，不是原作 canon。
- **设定无处可存**：`character` / `worldbuilding` / `event` 模型全部挂 `project_id`（用户自己的创作项目），没有挂在原作(reference)上的可复用 canon 存储。
- **wizard 误用原作**：现仅把 reference 当 `style_reference`（文风参考），注入 `writing_style` 文本。二创命门恰恰相反——**设定要忠于原作（锚定），文风反而可以是二创自己的**。
- **准确度难点无人处理**：长篇原作几十万字超上下文；同一实体跨章节多称呼需归并消歧；缺溯源导致 LLM 幻觉设定。

### 1.4 路线选择
| 路线 | 说明 | 结论 |
|---|---|---|
| A 轻量单遍提取 | 分块独立提取 + 字符串合并 | ✗ 消歧弱、无溯源、幻觉重，准确度最差 |
| **B 分层聚合+权威库+溯源** | 见本设计 | ✓ **采纳**，唯一真正解决长文本/消歧/防幻觉 |
| C 不建库，创作时 RAG 按需提取 | 复用向量化基础设施 | ✗ 形不成可校对全局 canon，覆盖不全、前后不一致；可作 B 的补充而非替代 |

> Gemini 架构咨询结论与 B 一致：分层提取与迭代聚合 / 动态实体索引与语义消歧 / 证据溯源(Source Grounding)。

## 2. 架构总览

挂在 `ReferenceNovel` 上的「设定提取」子系统，完全套用现有 `prose_pipeline` 范式：
异步 pipeline + `event_bus` SSE 进度 + `status` 状态机 + 子行表。
产出可溯源、可人工校对的设定圣经(canon)，供 wizard 二创创作锚定。

复用的现有设施：
- `ChunkService.split_text(content, chunk_size, overlap)` — 分块
- `prose_pipeline` + `prose_event_bus` — 异步编排 + SSE 进度 + 状态机 + `gather`/`return_exceptions` 容错范式
- `AIService.generate_text(prompt, provider, max_tokens)` — 单次 LLM 调用
- `wizard` 的 `_extract_json_array` — LLM 非法 JSON 输出容错

## 3. 数据模型（2 张新表，挂 reference）

### 3.1 `canon_entity` — 统一设定条目表（多态，仿 worldbuilding 的 `category + content` 思路）

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | PK | |
| `reference_id` | FK→reference_novels | **挂在原作上，跨项目复用** |
| `entity_type` | String | character / location / ability / faction / worldrule / event |
| `canonical_name` | String | 消歧后的权威名 |
| `aliases` | JSON | 所有别名/称呼，如 ["陛下","那妖道假扮的国王"] |
| `summary` | Text | 一句话设定 |
| `attributes` | JSON | 类型专属字段（角色:性格/关系/能力体系；能力:威力/限制/代价；势力:成员/立场…） |
| `source_refs` | JSON | **溯源**：`[{"chapter":..,"offset":..,"quote":".."}]` —— 防幻觉 + 人工核验抓手 |
| `importance` | String | critical / major / minor |
| `confidence` | Float | AI 提取置信度 |
| `review_status` | String | ai_extracted / user_verified / user_edited / user_added |
| `created_at` / `updated_at` | DateTime | |

> 实体间关系（角色关系网、事件因果链）MVP 先用 `attributes` 内 JSON 引用，不单开关系表。

### 3.2 `canon_extraction_job` — 提取任务（进度/SSE/状态机，仿 prose_project）

`id, reference_id(FK), status(pending/processing/done/failed), model, chunk_total, chunk_done, entity_count, error, created_at, updated_at`

## 4. 提取 Pipeline（4 阶段，套 prose_pipeline 编排）

1. **CHUNK** — `ChunkService.split_text`，章节优先、字数兜底（块调到 ~4-8k 字带 overlap），写入 `chunk_total`
2. **ATOMIC_EXTRACT** — 每块并行（`asyncio.gather` + 信号量限流，仿 prose）调 LLM，提取本块出现的实体，**强制带原文 quote + 章节定位**，输出结构化 JSON；逐块更新 `chunk_done` 并发 SSE 进度
3. **MERGE_DISAMBIGUATE** — 分层聚合：按 `entity_type` 分组，高阶 LLM 跨块归并消歧到权威实体，合并 `attributes`、保留全部 `source_refs`；实体多时**树状分批归并**避免再次超上下文
4. **PERSIST** — 落库 `canon_entity`(review_status=ai_extracted)，`canon_event_bus` 推 SSE 完成事件

### 4.1 容错
- 单块提取失败：记录、跳过、计 `failed`，不阻塞整体（仿 prose `gather(return_exceptions=True)`）
- LLM 输出非法 JSON：走 `_extract_json_array` 兜底 + 一次重试
- 长文本二次超限：分块上限 + 归并树状分批

## 5. 人工校对 UI

原作详情页（`ReferenceDetailView` 或等价）新增「**设定**」Tab：
- 按 `entity_type` 分组列出条目
- 每条可展开查看 **溯源原文引用**（`source_refs` 的 quote + 章节定位）
- 可编辑 / 删除 / 合并（多别名归并）/ 手动新增
- `review_status` 角标区分 AI提取 / 已校对 / 已编辑 / 手动添加

这是准确度的人工兜底闭环——溯源既防幻觉，又让用户能逐条核验纠错。

## 6. wizard 接入（设定锚定 ≠ 文风参考）

- wizard 请求新增 `canon_reference_id`（独立于现有 `reference_ids` 的文风参考）
- pipeline 把相关 `canon_entity`（角色/世界观规则/能力体系）作为 **必须遵守的事实约束** 注入 prompt，与 `style_reference` 的「文风参考」语义分开
- 「穿越乌鸡国国王如何活下去/成仙成佛」的主线问答即在这份锚定设定上推演
- MVP：按 `premise` 关键词 + 向量召回相关实体注入（复用现有向量化设施）

## 7. 测试

- `split` / `atomic_extract` / `merge_disambiguate` 各阶段单测
- 用 `reference_novels/` 小样本跑一次端到端
- **准确度回归基线**：`source_refs` 非空校验（每条 AI 提取的设定必须可溯源）

## 8. 范围边界（YAGNI）

**本 spec 只做**：提取建库（4 阶段 pipeline + 2 张表）+ 校对 UI + wizard 锚定接入。

**本 spec 不做**（后续独立 spec）：
- 增量提取（原作新增内容只提取增量并并入）
- 实体关系图谱可视化
- 二创笔法/脑洞库（愿景第②阶段）
