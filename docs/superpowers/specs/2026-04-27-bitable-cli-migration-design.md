# 设计文档：飞书数据源迁移到 bitable CLI 模式

**创建日期**：2026-04-27
**状态**：设计阶段（待用户审阅 → writing-plans）
**作者**：Claude（基于与用户的 8 轮 brainstorming）

---

## 1. 背景与动机

### 1.1 现状

剧本评审数据流：

```
飞书 sheet (URL[0]+URL[1])
  └─ data/get_feishu_doc.py  (02:00 cron)
       └─ uploads/外部待审核剧本.xlsx
            └─ script_rubric/pipeline/run.py
                 └─ parse_xlsx.py（按固定列号读取）
```

`script_rubric/config.py` 硬编码了 11 个评审员的列号映射（`REVIEWERS = [(name, score_col, comment_col), ...]`）。

### 1.2 问题

业务方启用了飞书"高级权限"模式（`is_advanced=true`），导致即便应用 `cli_a955fe3f1e7a9bce` 是文档协作者，列出数据表 API 仍返回 `code=0, items=[]`（静默拒绝）。原 bitable 的所有者无法配合关闭高级权限。

### 1.3 用户解决方案

用户在飞书里**手动克隆**原 bitable（每次产生新 token，且新 owner 是用户自己），关闭副本的高级权限，把副本 URL 提交给系统。

每次副本 token 不同 → 无法在代码里硬编码 token → 自动化流程不再可行。

### 1.4 目标

- **彻底废除**基于 sheet 的旧链路（包括 URL[0]、URL[1]、cron 调度、xlsx 中介）
- 建立一个 **CLI-only** 的工具，接受副本 URL 作为参数，端到端跑完同步与评审 pipeline
- rubric pipeline **直接读取 bitable 规范化 JSON**，不再依赖 xlsx 列号

### 1.5 非目标

- 不做 API/UI 触发（用户明确选 D：CLI only）
- 不保留 sheet 同步历史
- 不做记录跨副本对账（每次副本 record_id 都不一样，识别同条数据靠 title）

---

## 2. 架构

### 2.1 数据流

```
人类操作（每次同步前）：
  飞书内克隆原 bitable → 关高级权限 → 复制副本 URL
                          │
                          ▼
$ python data/sync_bitable.py <url> [--no-pipeline]
  │
  ├─ Step 1：解析 URL，提取 app_token（支持 /base/<token> 和 /wiki/<wiki_token>）
  ├─ Step 2：拉取 bitable
  │     ├─ GET /bitable/v1/apps/{token}              （元信息验证）
  │     ├─ GET /bitable/v1/apps/{token}/tables       （应有「冲量」「精品」两表）
  │     ├─ GET /bitable/v1/apps/{token}/tables/{tid}/fields   （字段名+类型）
  │     └─ GET /bitable/v1/apps/{token}/tables/{tid}/records  （翻页拉全）
  ├─ Step 3：规范化展平
  │     ├─ 「精品」→ {record_id, title, source_type, genre, submitter, status, overall_score, scores, comments, raw}
  │     └─ 「冲量」→ {record_id, title, ..., raw}（仅 dump，rubric 不读）
  ├─ Step 4：原子写入（写到 .tmp 后 rename）
  │     ├─ data/bitable_dumps/精品.json
  │     └─ data/bitable_dumps/冲量.json
  ├─ Step 5：追加同步历史
  │     └─ data/cli_sync_logs/sync_history.json
  └─ Step 6：串 rubric pipeline（默认开启，--no-pipeline 关闭）
        └─ python script_rubric/pipeline/run.py incremental
              └─ parse_bitable.py 读 data/bitable_dumps/精品.json
```

### 2.2 关键约束（从 brainstorming 收敛）

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据中介 | 彻底替换（rubric 直接读 JSON） | 用户明确（Q1=C） |
| 触发方式 | CLI only | 副本 token 不固定，无法定时（Q3=D） |
| 02:00 cron | 保留壳，停 job 注册 | 将来可能复活（Q4.1=B） |
| URL[1]「内部已签约待制作」 | 一并废弃 | 用户明确（Q4.2=A） |
| Rubric 触发 | 默认串，`--no-pipeline` 关 | 调试灵活（Q4.3=C） |
| 同步历史 | 独立 `data/cli_sync_logs/` + 自动追加 | 与 pipeline_history 字段风格一致（Q4.4=B） |
| 两表处理 | 仅「精品」进 rubric，「冲量」JSON dump | 「冲量」字段不全，硬塞会被 `MIN_SCORES_FOR_INCLUSION=3` 过滤为噪音（Q5=A） |
| 评审员配置 | 自动从字段名发现 `<人名>打分/点评` | bitable 命名稳定（Q6=A） |
| JSON 路径 | 固定路径覆盖 | 副本快照无回溯价值（Q7.1=A） |
| JSON 内容 | 规范化展平 | rubric 解耦 bitable schema（Q7.2=乙） |
| 旧 xlsx | 删除 | 切干净（Q8.1=A） |
| `parse_xlsx.py` + 旧测试 | 删除 | 死代码（Q8.2=A） |
| `get_feishu_doc.py` | 抽共享工具到 `feishu_common.py`，旧文件删 | token/wiki 解析仍可复用（Q8.3=C） |
| `scheduled_task.py` | 留壳删函数 | 8.4=乙 |

---

## 3. 组件清单

### 3.1 新增

| 文件 | 职责 | 大致行数 |
|------|------|--------|
| `data/sync_bitable.py` | CLI 入口：解析 URL → 拉数据 → 规范化 → 写文件 → 追加历史 → 可选串 pipeline | ~220 |
| `data/feishu_common.py` | 共享工具：`get_tenant_access_token`、`extract_token`（兼容 base/wiki）、`resolve_wiki_node`、`call`（带通用错误处理） | ~80 |
| `script_rubric/pipeline/parse_bitable.py` | 读 `data/bitable_dumps/精品.json`，自动发现评审员，输出 `Record` 对象列表（与原 `parse_xlsx.py` 输出 schema 一致） | ~120 |
| `script_rubric/tests/test_parse_bitable.py` | 替代 `test_parse_xlsx.py`，覆盖：基础解析、自动发现评审员、缺失字段处理、空 JSON、形态错误（fail-loud） | ~150 |

### 3.2 修改

#### `script_rubric/config.py`
- **删除**：`XLSX_PATH`、`XLSX_COLUMNS`、`REVIEWERS`
- **新增**：
  ```python
  BITABLE_DUMPS_DIR = PROJECT_ROOT / "data" / "bitable_dumps"
  BITABLE_RUBRIC_JSON = BITABLE_DUMPS_DIR / "精品.json"
  BITABLE_REFERENCE_JSON = BITABLE_DUMPS_DIR / "冲量.json"
  RUBRIC_TARGET_TABLE = "精品"  # 给 parse_bitable.py 文档用
  ```
- 保留：`SCORE_TIER_THRESHOLDS`、`MIN_SCORES_FOR_INCLUSION`、`HOLDOUT_RATIO` 等业务常量

#### `script_rubric/pipeline/run.py`
- 替换 `from .parse_xlsx import parse_xlsx, load_all_archives` 等 import 为 `from .parse_bitable import parse_bitable_json`
- 替换 4 处 `parse_xlsx(XLSX_PATH, ...)` 调用为 `parse_bitable_json(BITABLE_RUBRIC_JSON, ...)`
- 函数签名/返回值不变（对 `pass1_extract` 等下游零影响）

#### `backend/app/services/scheduled_task.py`
- 删除：`run_feishu_sync()`、`_trigger_pipeline_after_sync()`、对 `data.get_feishu_doc` 的 import
- 删除：调度器中 `add_job(run_feishu_sync, ...)` 调用
- 保留：`scheduler` 全局变量、`init_scheduler()`、`start_scheduler()`、`stop_scheduler()` 框架（空 scheduler，不注册 job）
- 保留：日志/历史读取函数（`get_sync_history`/`get_last_sync_info`）—— 是否仍被引用见 Open Item O3

### 3.3 删除

| 文件 | 备注 |
|------|------|
| `data/get_feishu_doc.py` | 被 `feishu_common.py` + `sync_bitable.py` 取代 |
| `uploads/外部待审核剧本.xlsx` | rubric 已不读它 |
| `script_rubric/pipeline/parse_xlsx.py` | 被 `parse_bitable.py` 取代 |
| `script_rubric/tests/test_parse_xlsx.py` | 测试目标已删除 |
| `script_rubric/tests/test_match_texts.py` | 它依赖 `parse_xlsx` 调用链 |

---

## 4. 数据契约

### 4.1 CLI 命令行接口

```
python data/sync_bitable.py <BITABLE_URL> [--no-pipeline] [--mode incremental|full]

参数：
  BITABLE_URL     形如 https://xxx.feishu.cn/base/<app_token>
                  也兼容 https://xxx.feishu.cn/wiki/<wiki_token>（自动 resolve）
  --no-pipeline   只拉数据并落地 JSON，不串 rubric pipeline
  --mode          rubric pipeline 模式（默认 incremental）

退出码：
  0  全流程成功
  1  bitable 拉取失败（权限/网络/URL 解析）
  2  规范化失败（表名找不到、字段缺失等）
  3  rubric pipeline 失败（CLI 自身已成功）
```

### 4.2 JSON 输出格式

#### `data/bitable_dumps/精品.json`

```json
{
  "synced_at": "2026-04-27T14:30:12+08:00",
  "source_app_token": "EyhfburjGa6q41s6Ck6c664Knnc",
  "source_table_id": "tblkvyapBqrMSQWa",
  "source_table_name": "精品",
  "total": 180,
  "reviewers": ["小冉", "贾酒", "47", "帕克", "Vicki", "千北", "步步"],
  "records": [
    {
      "record_id": "rec_xxx",
      "title": "高考750分断绝关系，全家后悔 1-3",
      "source_type": "改编",
      "genre": "女频",
      "submitter": "47",
      "status": "改",
      "overall_score": 77,
      "scores": {
        "小冉": 80,
        "贾酒": 75,
        "47": null,
        "帕克": 80,
        "Vicki": 75,
        "千北": 75,
        "步步": null
      },
      "comments": {
        "小冉": "这竟然是女频文？！？！？！...",
        "贾酒": "第一集，反派抢保送名额...",
        "47": "...",
        "帕克": "这个还蛮新颖的",
        "Vicki": "爽文了，但是一定要每一集...",
        "千北": "感觉一般，不是很吸引我",
        "步步": null
      },
      "raw_fields": { /* bitable 原 fields，保留以备追溯 */ }
    }
  ]
}
```

**说明**：
- `reviewers` 由 CLI 在规范化阶段从字段名自动发现（扫所有 `<人名>打分` 字段，要求 `<人名>点评` 也存在；落单的不计入）
- `scores[人名]` 在 bitable 里没填的记录用 `null`，rubric pipeline 内部按 `MIN_SCORES_FOR_INCLUSION=3` 过滤
- `raw_fields` 保留所有 bitable 原始字段，便于 debug 与未来扩展

#### `data/bitable_dumps/冲量.json`

字段集与精品不同（含「价格」「导演」等业务字段），但顶层结构一致；rubric 不读这份，仅供参考。

### 4.3 同步历史

`data/cli_sync_logs/sync_history.json` —— 倒序数组（最新在前），保留最近 50 条：

```json
[
  {
    "synced_at": "2026-04-27T14:30:12+08:00",
    "source_url": "https://e76yjr9njh.feishu.cn/base/EyhfburjGa6q41s6Ck6c664Knnc",
    "source_app_token": "EyhfburjGa6q41s6Ck6c664Knnc",
    "source_app_name": "外部待审核剧本 副本0427",
    "tables": {
      "冲量": {"table_id": "tblVeKJiaT7sRo3J", "records": 177, "fields": 21},
      "精品": {"table_id": "tblkvyapBqrMSQWa", "records": 180, "fields": 21, "reviewers_detected": 7}
    },
    "elapsed_sync_s": 12.4,
    "pipeline_triggered": true,
    "pipeline_result": {
      "success": true,
      "handbook_version": "v11",
      "elapsed_s": 612.5,
      "new_archives": 3
    },
    "success": true,
    "error": null
  }
]
```

字段结构参照原 `pipeline_history.json` 风格但更结构化。

---

## 5. 风险吸收（Gemini 外部审阅意见）

| 风险 | 来源 | 对应措施 |
|------|------|--------|
| **R1**：副本间 `record_id` 不稳定，无法跨副本对齐同一脚本 | Gemini #1 | spec 内明确：record_id 仅作**同一次同步内**的唯一键；rubric pipeline 跨副本识别同一脚本依赖 `title`（与原 xlsx 行为一致） |
| **R2**：用户在副本里改字段名时自动发现失效 | Gemini #2 | `parse_bitable.py` **fail-loud**：检测到 0 评审员或字段缺关键项（无 `title`/`overall_score`）时抛 `ValueError("字段命名变化：...")`；不静默继续 |
| **R3**：固定路径覆盖在崩溃时丢失旧数据 | Gemini #3 | 写 `精品.json.tmp` → `os.replace(..., 精品.json)`，保证原子性 |
| **R4**：硬编码"精品"表名限制扩展 | Gemini #4 | 表名抽到 `config.RUBRIC_TARGET_TABLE = "精品"`；改名只需改一处 |
| **R5**：飞书 API 错误提示不够友好 | Gemini #5 | CLI 检测到 `code=0, items=[]` 时打印明确错误："看起来高级权限未关闭——请在飞书副本权限设置里关闭'高级权限'后重试" |

---

## 6. 测试策略

### 6.1 单元测试（`script_rubric/tests/test_parse_bitable.py`）

- 基础：完整 JSON → 正确 `Record` 数量与字段
- 自动评审员发现：3 个评审员 → `record.scores` 包含 3 个 key
- 缺失关键字段：移除 `title` → `ValueError`
- 缺失 status/overall_score：单条记录跳过，不影响其他
- 0 评审员（所有 `<人名>打分` 字段被删）→ fail-loud
- 仅打分无点评（如「冲量」表的「47」）→ 该评审员被丢弃

### 6.2 集成测试（手工）

CLI 使用：
1. 拉副本 URL，预期：`bitable_dumps/*.json` 生成 + `cli_sync_logs/sync_history.json` 追加 + rubric pipeline 触发并生成新 handbook 版本
2. `--no-pipeline`：仅 JSON 落地，pipeline 不跑
3. 错误 URL：CLI 退出码 1，打印明确错误
4. 高级权限未关：CLI 退出码 1，打印 R5 中的提示

### 6.3 现有测试影响

- `tests/test_parse_xlsx.py`、`tests/test_match_texts.py` 删除
- `tests/test_extract_archive.py`、`tests/test_iterate_handbook.py` 等不依赖 `parse_xlsx`，预期照常通过（验证见 O2）

---

## 7. 部署/迁移注意

1. **先备份现有 xlsx**（即便选 8.1=A 删除）：以防计划执行后发现遗漏
2. **保留 `pipeline_history.json`**：rubric pipeline 自身的历史不变，新 CLI 历史在另一个文件
3. **第一次 CLI 跑通后**才执行删除清单（`get_feishu_doc.py`、`parse_xlsx.py` 等）
4. backend 容器是否需要 rebuild —— 见 O4

---

## 8. 实施前需验证的开放项（计划阶段处理）

| 项 | 说明 |
|---|---|
| **O1** 应用权限 | 应用 `cli_a955fe3f1e7a9bce` 是否已开通 `bitable:app:readonly`（开发者后台查；可借探测脚本验证） |
| **O2** 测试集影响 | `tests/test_extract_archive.py`、`tests/test_iterate_handbook.py` 等不依赖 `parse_xlsx` 的测试是否仍通过（实际运行验证） |
| **O3** scheduled_task 残留引用 | `scheduled_task.py` 的 `get_sync_history` / `get_last_sync_info` 是否被其他代码（API 路由、frontend）引用；如有引用决定保留还是迁移到 CLI 历史 |
| **O4** 容器同步 | 改动 backend 代码是否需 docker rebuild，还是 hot reload 生效（看 backend Dockerfile 与启动方式） |
| **O5** record 的 raw_fields 体积 | 「精品」180 条全保留 raw_fields 后 JSON 文件大小是否合理（估算后决定是否压缩或精简） |

## 9. 范围外（未来可能）

- 内容上传到对象存储/数据库（CLAUDE.md 指出"项目优先 docker 部署"，将来若数据量增长可考虑 PostgreSQL）
- 自动化（如：飞书机器人监听原 bitable 变化 → 触发用户同步）
- 副本生命周期管理（删旧副本，飞书也无 API）

---

## 附录 A：飞书 API 调用清单

| 调用 | 端点 | 用途 |
|------|------|------|
| 1 | `POST /open-apis/auth/v3/tenant_access_token/internal` | 获取 token |
| 2 | `GET /open-apis/wiki/v2/spaces/get_node?token=<wiki_token>` | （仅 wiki URL）解析为 bitable app_token |
| 3 | `GET /open-apis/bitable/v1/apps/{app_token}` | 校验 + 取 app 名 |
| 4 | `GET /open-apis/bitable/v1/apps/{app_token}/tables?page_size=100` | 列表数据表 |
| 5 | `GET /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields?page_size=100` | 字段定义 |
| 6 | `GET /open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500&page_token=...` | 全量记录（翻页） |

需求权限范围：`wiki:wiki:readonly`（已具备）+ `bitable:app:readonly`（验证见 O1）

---

## 附录 B：Brainstorming 历史问答

| Q | 选项 | 用户答 |
|---|------|--------|
| Q1 废除范围 | A/B/**C**/D | C：彻底替换数据中介 |
| Q3 提交方式 | A/B/C/**D** | D：CLI only |
| Q4.1 02:00 cron | A/**B**/C | B：保留壳，停 job |
| Q4.2 URL[1] | **A**/B | A：一并废弃 |
| Q4.3 自动串 pipeline | A/B/**C** | C：默认串，flag 关 |
| Q4.4 历史 | A/**B**/C | B：独立目录 + 新格式 |
| Q5 两表合并 | **A**/B/C | A：仅精品进 rubric |
| Q6 评审员 | **A**/B/C | A：自动发现 |
| Q7.1 文件布局 | **A**/B/C | A：固定路径覆盖 |
| Q7.2 内容形态 | 甲/**乙** | 乙：规范化 |
| Q8.1 旧 xlsx | **A**/B/C | A：删 |
| Q8.2 parse_xlsx + 测试 | **A**/B/C | A：全删 |
| Q8.3 get_feishu_doc.py | A/B/**C** | C：抽共享工具 |
| Q8.4 scheduled_task 内函数 | 甲/**乙** | 乙：删函数留壳（默认值，用户同意） |
