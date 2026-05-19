# 飞书 bitable 书级去重设计

**日期**：2026-05-19
**作者**：用户 + Claude（jrient session）
**状态**：草案

## 背景

源端飞书 base 有访问权限限制，无法稳定给当前飞书 app 授权。实际工作流是：每次手工复制一份新副本到一个无权限限制的空间，给当前 app 临时授权，由 `script_rubric.feishu.sync_bitable` 拉取。

**链接每次都不一样**，但内容是**同一批"书"的增量更新**。

现有存储层（`script_rubric/data/bitable_records/{table_id}/{record_id}.json`）按 `table_id + record_id` 去重 —— 这两个 ID 都是飞书侧分配，**每个新副本都会生成新值**。导致：

- 本地已累积 7 个 `table_id` 目录，来自 3 个不同 `app_token`
- "精品"和"冲量"各出现 3 次、"内部本"1 次
- 下游 `parse_bitable` 只按书名（title）认书，会拿到大量重复

存储模型（`table_id + record_id`）与业务模型（书）不匹配。

## 目标

让多次"复制副本 + 拉取"累积下来的数据，在业务视图层（`bitable_rubric.json`）按**书**唯一，最新拉到的为准。

非目标：

- 不重构存储层（per-record 文件保留原样）
- 不修改下游 `parse_bitable` / pipeline
- 不限制飞书侧表名（不再用 allowlist 过滤）

## 设计决策

经与用户澄清确定：

| 决策点 | 选择 | 备选 |
|---|---|---|
| Dedup key | 书名（单独） | 书名+表名；书名+业务字段 |
| 冲突合并策略 | 全字段覆盖，不合并 | 字段级合并 |
| Allowlist | 拉全部表（默认 `None`） | 默认 `{精品, 冲量}` |
| 来源 trace | 只留最近一次 `(app_token, table_id, record_id, synced_at)` | 完整历史；不留 |
| 历史重复数据 | 改造后跑一次 dedup（rebuild_index 层），不动原始文件 | 物理清理；不动 |
| Dedup 层位置 | 纯 index 层（rebuild_index 内） | sync 时；双层 raw+canonical |

## 架构

```
飞书副本URL ──► fetch_bitable(allowlist=None)
                      │
                      ▼
              sync_table_records ─► per-record store（原样累积）
                                        bitable_records/{table_id}/{record_id}.json
                                        bitable_records/{table_id}/_meta.json
                                        │
                                        ▼
                              rebuild_index ─► bitable_rubric.json
                                ↑↑↑           （按书名去重后的视图）
                                新增 dedup 层
```

变化点（共三处）：

1. `script_rubric/feishu/sync_bitable.py`：
   - `EXPECTED_TABLES = None`（拉全部表，不过滤）
   - `fetch_bitable()` 循环里：`if allowlist is not None and table_name not in allowlist: skip`（即 `None` 表示不过滤）
   - per-source 的 `tables` 字段**仍然生效**：用户可以为某个 source 显式限制，留作未来兜底，未指定时走默认（拉全部）
2. `script_rubric/feishu/record_store.py`：`rebuild_index()` 内部加 book-level dedup
3. 无下游改动；per-record store 不变

## Dedup 逻辑

`rebuild_index()` 新流程：

1. 遍历所有 per-record 文件（含历史累积的 7 个 `table_id` 目录）
2. 对每条 record，提取：
   - `title` = 5 个候选字段里第一个非空（`书名` / `文本` / `剧本名称` / `剧本` / `标题`）
   - `table_name` = 该 `table_id` 的 `_meta.json` 里的 `table_name`
   - `synced_at` = `record._synced_at`
   - `source_app_token` / `table_id` / `record_id`
3. 按归一化后的 title 作 key 分组（归一化：`strip()` + 去掉 `《》` 前后空格）
4. 每组取 `_synced_at` 最大者作 winner；tiebreak 按 `record_id` 字典序更大者
5. winner 写入 index，附加 `_last_source = {app_token, table_id, record_id}`
6. 无 title 的 record 全部丢弃（原本下游也认不到）
7. 被淘汰的 records 记入 `_dedup_dropped`（仅 title + kept_from / dropped_from 来源标识，给审计）

**表归属**：以 winner 所在 `table_name` 为准。winner 在哪张表，索引里就把它放在哪张表的 records 数组里。

## 输出 schema（向后兼容）

```json
{
  "synced_at": "...",
  "app_token": "<最近一次拉的 app_token>",
  "tables": [
    {
      "table_id": "<最新出现的 table_id>",
      "table_name": "精品",
      "fields": [...],
      "records": [<winner records>]
    },
    ...
  ],
  "_index_rebuilt_from": "<RECORDS_ROOT 绝对路径>",
  "_dedup_stats": {
    "total_files": <int>,
    "unique_books": <int>,
    "dropped_duplicates": <int>,
    "skipped_no_title": <int>
  },
  "_dedup_dropped": [
    {
      "title": "...",
      "kept_from": "table_id/record_id",
      "dropped_from": "table_id/record_id"
    }
  ]
}
```

下游兼容性：
- `synced_at` / `app_token` / `tables[].records` 字段名与结构不变
- record 内多了 `_last_source`，不影响 `parse_bitable`（它只读 `fields`）

**表归属选择**：同表名的多个 `table_id` 目录（如 3 个"精品"目录）合并为索引里的单条 table 项；`table_id` 取贡献 winner 最多的那个目录的 id（确定性）；`fields` 取最近 `_updated_at` 的那个 meta 的。

## 错误处理与边界

| 情形 | 处理 |
|---|---|
| 飞书侧 list_tables 返回空（高级权限 silent failure） | 现有 `fetch_bitable` 已报 RuntimeError，保持 |
| 副本里某张表 title 字段命名特殊（5 候选都没命中） | 该 record 跳过、不进 dedup，计入 `skipped_no_title` |
| 两条 record 同 title 且 `_synced_at` 完全相同 | 按 `record_id` 字典序更大者 |
| 老 per-record 文件没有 `_synced_at` | 视为 `"1970-01-01T00:00:00"`，必然被新数据覆盖 |
| 多张表都有同名书（同副本内） | 都参与 dedup，取最新；正常不出现 |
| 书名前后空格 / 《》差异 | 归一化 key；保留原始 title 在 record 里 |
| index 写盘失败 | 维持现有 tmp+rename 原子写 |

## 回滚

去重逻辑全部在 `rebuild_index()` 内部，per-record 原始数据不动。出问题：
1. revert 修改
2. 重跑 `python3 -m script_rubric.feishu.sync_bitable --all`（无新数据则只跑 rebuild）
3. 数据完全恢复到旧行为

## 测试

新增 `script_rubric/tests/test_book_dedup.py`：

| 测试 | 验证 |
|---|---|
| `test_dedup_keeps_latest_by_synced_at` | 三个 record 同 title 不同时间，winner 是最新 |
| `test_dedup_tiebreak_by_record_id` | _synced_at 相同时按 record_id 字典序 |
| `test_dedup_normalizes_title` | `《某书》`、`某书 `、`某书` 算同一本 |
| `test_dedup_cross_table_winner_wins_in_its_table` | 跨表移动：winner 在「精品」时，index 中「冲量」不含该书 |
| `test_dedup_drops_no_title_records` | 无 title 的脏 record 不进 index，计入 skipped_no_title |
| `test_dedup_stats_block_emitted` | `_dedup_stats` / `_dedup_dropped` 字段存在且数字正确 |
| `test_rebuild_idempotent` | 同一目录 rebuild 两次，去重后内容 byte-identical（忽略 `synced_at` 头部时间戳） |
| `test_legacy_records_without_synced_at` | 老 record 无 `_synced_at` 时被新 record 覆盖 |
| `test_same_table_name_multiple_dirs_merged` | 3 个 `table_id` 目录都叫"精品"，索引里合并成 1 条 table 项 |

复用现有 `test_merge_bitable.py` 的 fixture 风格。

**验收（人工）**：
1. 跑一次 `rebuild_index` over 现有 7 个目录
2. diff 老 `bitable_rubric.json` 和新输出
3. 人工抽查：3 张"精品"里都有的某本书，新输出里只出现一次，且 `_last_source` 指向最新那次
4. 总书数 ≈ unique titles 数（应当显著少于旧的 total_records）

## 范围之外

- 不动 `sync_table_records`（继续按 `table_id + record_id` 落盘）
- 不动下游 `parse_bitable` / `match_texts` / 评分 pipeline
- 不做 per-record 物理清理（用户明确选了"改造后跑一次 dedup 迁移"= rebuild 阶段，不动原始文件）
- 不做飞书侧授权自动化（无法实现，用户每次手动授权）
- 不引入 prune 命令（旧 record 永久保留作 audit trail）
