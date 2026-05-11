# 剧本改编系统 设计文档

- 创建日期：2026-05-11
- 状态：待评审
- 作者：jrient + Claude（brainstorming）
- 关联评审：Gemini 技术 review（已合并）

## 1. 背景与目标

为现有 `novel-writer` 平台新增一个独立的"剧本改编"模块，解决以下场景：

> 用户已有一份成型剧本（txt/docx），希望快速改写其中的人名、地名、关键道具、时代背景，但**剧情节奏（场次结构、冲突点、情感拐点、对白节奏）不变**。

定位：与现有 `剧本工作台`、`文本扩写`、`剧本评分` 平级的独立菜单项。新数据模型，与 `ScriptProject` 解耦。

## 2. 范围

### 2.1 MVP 范围

- 文件导入（txt/docx，最多 200,000 字）或粘贴
- AI 自动抽取实体表（人物 / 地点 / 道具 / 时代关键词）
- 用户在表内补填新值；可锁定行
- 三档改编强度（替换 / 润色 / 重铸），单滑杆切换
- 自由文本"改编意图"+"新时代/世界设定"两个全局字段
- 按"场"切分（正则优先，LLM fallback）
- 并发分场改写，SSE 推前端进度
- 场列表 + 抽屉式 diff/手改/单场重跑 工作台
- 全场重跑产生新版本，多版本可切换
- 一键导出 txt/docx

### 2.2 明确不做（推迟到后续阶段）

- 节奏一致性自动校验模块（结构指标对比、LLM 反检）
- 多版本 side-by-side 对比视图
- "改编项目转为 ScriptProject 继续加工" 链路
- 协同编辑、评论、分享
- 跨项目"全局实体库"
- 自定义模型路由 UI（先用代码常量）
- 批量改编（一次跑 N 套映射）
- 实时 token 配额拦截
- 多 worker 分布式调度（MVP 假设单 worker 部署）

## 3. 数据模型

新增 4 张表，全部以 `adaptation_` 前缀，不复用 `script_*` 表。

### 3.1 `adaptation_projects`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| user_id | FK users.id | |
| title | varchar(200) | |
| source_filename | varchar(255) | 可空（粘贴场景） |
| source_text | text | 原文全文，**写入后只读** |
| intent | text | 用户写的"改编意图"，可空 |
| intensity | int | 1=替换 / 2=润色 / 3=重铸 |
| era_target | text | 新时代/世界设定描述，可空 |
| status | varchar(20) | parsing / extracting / extract_failed / split_failed / ready / generating / done / failed |
| metadata | jsonb | 场切分边界、每场摘要、人物性格标签等 |
| created_at, updated_at | timestamp | |

`metadata` 形如：
```json
{
  "scene_boundaries": [{"index": 0, "start": 0, "end": 1280, "title": "场1 长安城外"}],
  "scene_summaries": ["主角与师父告别...", "..."],
  "character_traits": [{"name": "李铁柱", "tags": ["重情义", "冲动", "口头禅:这都行?"]}],
  "split_method": "regex" | "llm" | "fallback_single"
}
```

### 3.2 `adaptation_mapping_entries`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| project_id | FK | |
| entity_type | varchar(20) | person / place / prop / era_term / other |
| original_text | varchar(200) | |
| replacement_text | varchar(200) | nullable，空=待 AI 建议或用户填 |
| locked | bool | 用户锁定后重新抽取不覆盖；REWRITE 阶段在 prompt 中标为强约束 |
| notes | text | 用户备注，如"改成女性" |
| order_index | int | |

### 3.3 `adaptation_versions`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| project_id | FK | |
| version_no | int | 项目内自增 |
| triggered_by | varchar(20) | full_run（仅此一种创建新 version） |
| prompt_overrides | jsonb | 本次跑额外加的全局提示词 |
| status | varchar(20) | running / done / partial / failed |
| stats | jsonb | { total_scenes, succeeded, failed, total_tokens, started_at, completed_at } |
| mapping_snapshot | jsonb | 跑这次时整张映射表的副本（含 locked 标记），保证审计可追溯 |
| error | text | 顶层失败原因（如全部场失败） |
| created_at, completed_at | timestamp | |

### 3.4 `adaptation_scene_results`

| 列 | 类型 | 说明 |
|---|---|---|
| id | int PK | |
| version_id | FK | |
| scene_index | int | 0-based，对应 metadata.scene_boundaries 顺序 |
| original_scene_text | text | 当时的原文片段（冗余存储，便于 diff，不依赖 boundary 漂移） |
| rewritten_scene_text | text | nullable |
| scene_title | varchar(200) | |
| status | varchar(20) | pending / running / done / failed / manual_edited |
| error | text | |
| token_used | int | |
| line_count_delta_pct | float | 三档都计算 = (new_lines - orig_lines)/orig_lines；仅作记录与高亮，不阻塞（阈值见 §4.4） |
| manual_edits | jsonb | `[{at, type:"manual"|"rerun", before, after, prompt?}]` |
| updated_at | timestamp | |

唯一索引：`(version_id, scene_index)`。

## 4. 流水线设计

```
[Stage 1] PARSE      上传/粘贴 → file_parser → source_text 落盘
[Stage 2] EXTRACT    LLM 抽实体表 + 顺带产人物性格标签 → mapping_entries + project.metadata
[Stage 3] SPLIT      正则切场，命中 ≥2 用正则；否则 LLM fallback → project.metadata.scene_boundaries
                     ↓ 用户在创建页填映射 / 选强度 / 写意图 / 写新设定
                     ↓ 用户点"开始改编"
[Stage 4] REWRITE    新建 version → 预创建 N 个 scene_results → asyncio.Semaphore 并发
                     → 每场完成立即 update DB + SSE 推前端
                     → 全部完成 update version.status
                     ↓ 用户审阅
                     ↓ 单场重跑 / 手改保存 / 全场重跑（=新 version）
```

### 4.1 Stage 1 PARSE

- 复用 `app/services/file_parser.py`，但解析阶段的字数上限改读 `ADAPTATION_MAX_CHARS`（默认 200,000），不影响其他模块的 30,000 限制。
- 解析失败 → 4xx，不落 project。

### 4.2 Stage 2 EXTRACT

- 一次 LLM 调用，prompt 要求输出 JSON：
  ```json
  {
    "entities": [{"type":"person","text":"李铁柱","count":42,"sample_context":"..."}],
    "character_traits": [{"name":"李铁柱","tags":["重情义","口头禅:这都行?"]}]
  }
  ```
- 失败：`project.status = extract_failed`，前端"重试抽取"按钮；自动重试上限 1 次。
- 模型走现有 `script_ai_service.get_provider()`，可被 `ADAPTATION_EXTRACT_MODEL` 覆盖。
- 重抽时：`locked=True` 的 mapping_entries **不删除不覆盖**，新抽出的实体若与现有 `original_text` 重复也跳过。

### 4.3 Stage 3 SPLIT

- 正则模式（按命中先后）：
  ```
  ^场\s*\d+
  ^第[一二三四五六七八九十百\d]+场
  ^INT\.|^EXT\.
  ^\d+\.\s*[内外]景
  ```
- 命中 ≥2 → 正则切，每段 title 取段首到换行符。
- 命中 <2 → LLM fallback：仅请求模型返回 `[{start_offset, end_offset, title}]`，**不重写文本**，省 token。
- LLM fallback 也失败 → 把全文当 1 场，标 `metadata.split_method = "fallback_single"`，前端给黄条提示。
- 切场结果落 `project.metadata.scene_boundaries`，不预写 scene_results。
- 用户可触发"重新切场"，等价于 Stage 3 重跑。

### 4.4 Stage 4 REWRITE

**触发：** `POST /api/adaptation/projects/{id}/runs`

**步骤：**
1. 读 `project.metadata.scene_boundaries`，读当前 mapping_entries
2. 写 version 行（`status=running`，`mapping_snapshot=[当前所有 mapping_entries 的快照]`）
3. 为每个场预创建 scene_result（`status=pending`，`original_scene_text` 取当时的原文片段）
4. 用 `asyncio.Semaphore(ADAPTATION_REWRITE_CONCURRENCY)` 并发跑每场
5. 每场完成 → update scene_result + 经一个 in-process pub/sub 推到 SSE → 前端
6. 全部跑完 → version.status = `done` / `partial` / `failed`

**单场 prompt 结构（按 intensity 分支）：**

公共 header：
- 角色：剧本改编工程师
- 全局映射表（明确标注 `[LOCKED]` 的映射项必须严格替换）
- era_target、intent
- 上一场 1-2 句摘要（首场跳过；摘要从 `project.metadata.scene_summaries` 取）
- 涉及到本场的人物性格标签（按本场原文中出现的人名匹配 metadata.character_traits）

按 intensity 不同的 body：
- **档1（替换）：** "仅做精准实体替换，处理同名消歧、称呼一致性、代词一致性。**禁止**改动其他词。"
- **档2（润色）：** "做替换 + 对受替换影响的句子做最小润色。**禁止增删对白行数**；**对白行数必须等于原文**。"
- **档3（重铸）：** "按 era_target 重写场景中的物件/职业/动作/语言风格。必须保留：出场人物功能、冲突点、情感拐点、场内台词数量在原文 ±20% 以内、场次顺序。"

**单场后处理（不阻塞，仅记录）：**
- 计算 `line_count_delta_pct`（按"\n"且非空行计数）
- 档1：>0% 标 warning
- 档2：>5% 标 warning
- 档3：>20% 标 warning
- warning 不影响 status，前端高亮黄圈

### 4.5 子流程：单场重跑

- 端点：`POST /api/adaptation/runs/{vid}/scenes/{idx}/rerun`，可携带 `extra_prompt`
- 不新建 version
- 该 scene_result 状态变 `running` 期间拒绝二次 rerun（409）
- 完成后追加一条 `manual_edits = {type:"rerun", at, prompt, before, after}`
- 触发 SSE 单场推送

### 4.6 子流程：手改保存

- 端点：`PATCH /api/adaptation/runs/{vid}/scenes/{idx}`
- 直接更新 `rewritten_scene_text`，状态置 `manual_edited`
- 追加 `manual_edits = {type:"manual", at, before, after}`

### 4.7 应用启动恢复

启动时清理：
- `adaptation_versions.status = running` 且 `created_at < now - 1h` → 标 `failed`，error="服务重启时跑步中断"
- 对应 `scene_results.status = running` → 标 `failed`

## 5. API

新增 `app/routers/adaptation.py`，挂在 `/api/adaptation`。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /projects | 创建（multipart 上传文件 或 JSON 粘贴） |
| GET | /projects | 列表（仅自己的） |
| GET | /projects/{id} | 详情（含 mappings、scene_boundaries、versions 概览） |
| PATCH | /projects/{id} | 改 title/intent/intensity/era_target |
| DELETE | /projects/{id} | 级联删除 versions/scenes/mappings |
| POST | /projects/{id}/extract | 触发实体抽取（保留 locked） |
| PUT | /projects/{id}/mappings | 整表 PUT |
| POST | /projects/{id}/mappings/suggest | 让 AI 批量建议空 replacement |
| POST | /projects/{id}/split | 触发/重新切场 |
| POST | /projects/{id}/runs | 新建一次全场改编 → 返回 version_id |
| GET | /projects/{id}/runs | 该项目所有 versions 列表 |
| GET | /runs/{vid} | 版本详情含所有 scene_results |
| GET | /runs/{vid}/stream | SSE：跑过程中场级进度 |
| POST | /runs/{vid}/scenes/{idx}/rerun | 单场重跑（body: {extra_prompt}） |
| PATCH | /runs/{vid}/scenes/{idx} | 手改保存 |
| GET | /runs/{vid}/export | query: format=txt\|docx |

权限：所有端点均校验 `project.user_id == current_user.id`。

## 6. 前端

新增 3 个 view + 路由：

| 路径 | 组件 | 用途 |
|---|---|---|
| /adaptation | AdaptationListView.vue | 项目列表 |
| /adaptation/create | AdaptationCreateView.vue | 创建+映射表+切场预览 |
| /adaptation/workbench/:id | AdaptationWorkbenchView.vue | 工作台 |

新增 API 客户端：`frontend/src/api/adaptation.ts`。

布局原则（按用户偏好，禁止左右分屏）：
- 创建页：上下堆叠的 4 个区块（标题导入 / 实体映射表 / 强度+意图+设定 / 切场预览）
- 工作台：顶部条 + 主体场列表 + 抽屉（点击场出来，覆盖在场列表上方）
- 抽屉内：上下堆叠 tab（原文 / 改编后 / Diff）

工作台关键交互：
- 顶部 SSE 进度条：跑改编时出现，显示 `已完成 N/M 场`，每场完成场列表对应行状态点变化
- 场列表行：场号 + 标题 + 状态点 + line_count_delta% 高亮 + [快速重跑] 按钮
- 抽屉 Diff：使用 `diff-match-patch` 或简单行级 diff
- 抽屉底部：[手改保存] [单场重跑] [恢复到 AI 版]
- 顶部"全场重跑"按钮：弹窗确认+可填全局 extra_prompt → 创建新 version
- 版本切换下拉：列出所有 version，切换不影响后台跑

SSE 客户端断线处理：自动重连后调 `GET /runs/{vid}` 拉最新 scene_results 重建 UI。

## 7. 错误处理

| 失败位置 | 表现 | 处理 |
|---|---|---|
| 文件解析失败 | 编码识别失败/超字数上限 | 4xx，不落 project；前端弹具体错因 |
| 实体抽取失败 | LLM 超时/JSON 解析错 | project.status=extract_failed；前端"重试抽取"；自动重试 1 次 |
| 切场全失败 | 罕见 | 降级单场+黄条提示 |
| 单场改写失败 | timeout/限流 | scene_result.status=failed；version 仍可 done(partial)；用户单场重跑 |
| SSE 断流 | 前端断网 | 重连后 GET /runs/{vid} 恢复 UI |
| 重复触发 | 用户疯狂点 | running 状态拒绝二次（409） |
| 服务重启中断 | running 半天 | 启动 hook 清理 stale running |

## 8. 配置

`app/core/config.py` 新增：

```python
ADAPTATION_MAX_CHARS = 200_000
ADAPTATION_REWRITE_CONCURRENCY = 5
ADAPTATION_PER_SCENE_TIMEOUT_SEC = 90
ADAPTATION_EXTRACT_MODEL: str | None = None  # None = 走默认 provider
ADAPTATION_REWRITE_MODEL: str | None = None
ADAPTATION_STALE_RUN_CLEANUP_AGE_SEC = 3600
```

均可被环境变量覆盖。

## 9. 测试

### 9.1 后端 pytest

- `tests/test_adaptation_split.py` — 正则命中 / fallback / 边界 case
- `tests/test_adaptation_pipeline.py` — mock LLM，验证 4 阶段状态流转、partial 失败、并发上限
- `tests/test_adaptation_versioning.py` — mapping_snapshot 写入、单场重跑/手改不新建 version、stale 清理
- `tests/test_adaptation_api.py` — 权限隔离、SSE endpoint 基本流、所有路径的 4xx 路径

### 9.2 前端

不新增单测；提供手测清单（在实施 plan 中给出）：
- 创建项目（上传 + 粘贴两条路径）
- 实体抽取与映射编辑（含 lock 行）
- 三档强度各跑一次
- 单场重跑 + extra_prompt
- 手改保存
- 全场重跑 → 版本切换
- SSE 断线重连
- 导出 txt/docx 内容正确

## 10. 上线决策与已知限制

- **MVP 假设单 worker 部署**：`asyncio.Semaphore` 与 in-process SSE pub/sub 不跨 worker。多 worker / 分布式时需迁移到 Redis 任务状态 + 队列，留作 v2。
- **节奏校验仅做行数 delta 高亮**，结构化校验/LLM 反检留 v2。
- **跨项目实体库** 留 v2。
- **mapping_snapshot 是 jsonb 完整副本**，若映射表过大（>1000 行）会冗余；MVP 不优化。

## 11. 与现有模块关系

- 复用 `app/services/file_parser.py`（仅放宽字数上限读取）
- 复用 `app/services/script_ai_service.py` 的 provider 路由
- 复用现有用户认证 / 中间件 / 异常处理
- 不依赖 `ScriptProject` / `ScriptNode` / 评分模块
- 前端复用 Element Plus、现有 `frontend/src/api/` 客户端模板

## 12. 验收标准

- 用户能在 5 分钟内：上传剧本 → 看到实体表 → 填几个新值 → 选强度 → 点开始 → 看到场列表跑完 → 导出
- 单 worker 下同时支持 ≥2 个项目并行跑改编互不干扰
- 测试覆盖 §9.1 全部用例通过
- 一份 5 万字剧本（约 30-50 场）档2 改编耗时 < 3 分钟（基于现有 deepseek-v4-pro 单次 1-2s 的实测）
