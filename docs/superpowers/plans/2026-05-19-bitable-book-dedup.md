# 飞书 bitable 书级去重实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让多次拉取的飞书副本数据在 `bitable_rubric.json` 视图层按书名唯一、最新为准，per-record 原始文件不动。

**Architecture:** 在 `script_rubric/feishu/book_dedup.py` 新建纯函数模块（title 归一化、winner 选择）。改造 `record_store.rebuild_index()` 调用 dedup 模块输出去重后的 index。改 `sync_bitable` 的 `EXPECTED_TABLES = None`（拉全部表）。下游 `parse_bitable` 不变。

**Tech Stack:** Python 3.x, pytest, pathlib, datetime；现有 `script_rubric/feishu/` 模块结构。

**Spec:** `docs/superpowers/specs/2026-05-19-bitable-book-dedup-design.md`

## 关键约束（实现前必读）

1. **per-record 文件原样不动** — 所有 dedup 在内存里做，仅影响 `rebuild_index()` 输出
2. **下游 `parse_bitable.EXPECTED_TABLES` 不能改** — 那是评分管线过滤器，与 sync 层的 allowlist 是两个独立的常量；本计划只改 `sync_bitable.py` 里的 `EXPECTED_TABLES`
3. **title 字段优先级与下游一致** — 5 个候选：`书名` / `文本` / `剧本名称` / `剧本` / `标题`（与 `feishu_common.TITLE_FIELD_CANDIDATES` 一致）
4. **复用已有 `_extract_record_title`**（在 `feishu_common.py`），不要重写

## File Structure

| 文件 | 责任 | 操作 |
|---|---|---|
| `script_rubric/feishu/book_dedup.py` | 纯函数：title 归一化、winner 选择、按书 dedup（不依赖 IO） | **新建** |
| `script_rubric/feishu/record_store.py` | `rebuild_index()` 改造：dedup 后再写盘 | **改** |
| `script_rubric/feishu/sync_bitable.py` | `EXPECTED_TABLES = None`；`fetch_bitable` 过滤逻辑兼容 None | **改** |
| `script_rubric/tests/test_book_dedup.py` | 单测 + 集成测试 | **新建** |

每个 Task 自包含、可独立 commit。

---

## Task 1: dedup 纯函数模块

**Files:**
- Create: `script_rubric/feishu/book_dedup.py`
- Test: `script_rubric/tests/test_book_dedup.py`

- [ ] **Step 1: 写失败测试 — title 归一化**

新建 `script_rubric/tests/test_book_dedup.py`：

```python
"""书级去重逻辑单测。"""

from script_rubric.feishu.book_dedup import (
    normalize_title,
    select_winner,
    dedup_by_book,
)


class TestNormalizeTitle:
    def test_strip_whitespace(self):
        assert normalize_title("  某书  ") == "某书"

    def test_strip_book_brackets(self):
        assert normalize_title("《某书》") == "某书"

    def test_strip_brackets_and_whitespace(self):
        assert normalize_title("  《某书》 ") == "某书"

    def test_empty_returns_empty(self):
        assert normalize_title("") == ""

    def test_none_returns_empty(self):
        assert normalize_title(None) == ""

    def test_inner_whitespace_kept(self):
        assert normalize_title("某 书") == "某 书"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py -v`
Expected: `ModuleNotFoundError: No module named 'script_rubric.feishu.book_dedup'`

- [ ] **Step 3: 实现 normalize_title**

新建 `script_rubric/feishu/book_dedup.py`：

```python
"""
书级去重纯函数模块
====================

把多次拉取累积的 per-record 数据按书名去重，最新 _synced_at 胜出。
全部为纯函数，不依赖 IO，便于单测。
"""

from __future__ import annotations

from script_rubric.feishu.feishu_common import _extract_record_title


def normalize_title(title: str | None) -> str:
    """归一化书名：去前后空格、剥掉《》。inner 空格保留。

    用作 dedup key 的稳定化处理。
    """
    if not title:
        return ""
    s = title.strip()
    if s.startswith("《") and s.endswith("》"):
        s = s[1:-1].strip()
    return s
```

- [ ] **Step 4: 运行 normalize_title 测试确认通过**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestNormalizeTitle -v`
Expected: 6 passed

- [ ] **Step 5: 写失败测试 — select_winner**

追加到 `test_book_dedup.py`：

```python
class TestSelectWinner:
    def _rec(self, record_id, synced_at, title="某书"):
        return {
            "fields": {"书名": title},
            "_record_id": record_id,
            "_synced_at": synced_at,
            "_source_table_id": "tid_x",
        }

    def test_latest_synced_at_wins(self):
        a = self._rec("r1", "2026-05-01T10:00:00")
        b = self._rec("r2", "2026-05-18T10:00:00")
        c = self._rec("r3", "2026-05-07T10:00:00")
        winner, dropped = select_winner([a, b, c])
        assert winner is b
        assert set(d["_record_id"] for d in dropped) == {"r1", "r3"}

    def test_tiebreak_by_record_id_dictionary_order(self):
        same_time = "2026-05-18T10:00:00"
        a = self._rec("r_aaa", same_time)
        b = self._rec("r_zzz", same_time)
        winner, _ = select_winner([a, b])
        assert winner is b

    def test_missing_synced_at_loses_to_anything(self):
        old = self._rec("r1", "")
        old.pop("_synced_at")
        new = self._rec("r2", "2020-01-01T00:00:00")
        winner, _ = select_winner([old, new])
        assert winner is new

    def test_single_record_is_winner(self):
        rec = self._rec("r1", "2026-05-18T10:00:00")
        winner, dropped = select_winner([rec])
        assert winner is rec
        assert dropped == []
```

- [ ] **Step 6: 运行测试确认失败**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestSelectWinner -v`
Expected: `ImportError: cannot import name 'select_winner'`

- [ ] **Step 7: 实现 select_winner**

追加到 `book_dedup.py`：

```python
_EPOCH_FALLBACK = "1970-01-01T00:00:00"


def _sort_key(record: dict) -> tuple[str, str]:
    """winner 选择排序 key：(_synced_at, _record_id)，缺失 _synced_at 用 epoch。"""
    synced_at = record.get("_synced_at") or _EPOCH_FALLBACK
    record_id = record.get("_record_id") or record.get("record_id") or record.get("id") or ""
    return (synced_at, record_id)


def select_winner(records: list[dict]) -> tuple[dict, list[dict]]:
    """从一组同 title 的 records 中选 winner。

    规则：_synced_at 最大者；tiebreak 取 _record_id 字典序更大者。
    缺失 _synced_at 视为 epoch（必然输给任何有时间戳的）。

    Returns:
        (winner, dropped_list)
    """
    if not records:
        raise ValueError("select_winner: empty records")
    if len(records) == 1:
        return records[0], []
    sorted_recs = sorted(records, key=_sort_key)
    winner = sorted_recs[-1]
    dropped = sorted_recs[:-1]
    return winner, dropped
```

- [ ] **Step 8: 运行测试确认通过**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py -v`
Expected: 10 passed (6 + 4)

- [ ] **Step 9: 写失败测试 — dedup_by_book**

追加到 `test_book_dedup.py`：

```python
class TestDedupByBook:
    def _rec(self, record_id, synced_at, title, table_id="tid_x", app_token="app_x"):
        return {
            "fields": {"书名": title},
            "_record_id": record_id,
            "_synced_at": synced_at,
            "_source_app_token": app_token,
        }, table_id

    def test_no_duplicates_no_op(self):
        a, _ = self._rec("r1", "2026-05-01T10:00:00", "A")
        b, _ = self._rec("r2", "2026-05-01T10:00:00", "B")
        winners, dropped, skipped = dedup_by_book([(a, "tid_a"), (b, "tid_b")])
        assert len(winners) == 2
        assert dropped == []
        assert skipped == 0

    def test_dup_titles_keep_latest(self):
        old, _ = self._rec("r1", "2026-05-01T10:00:00", "某书")
        new, _ = self._rec("r2", "2026-05-18T10:00:00", "某书")
        winners, dropped, skipped = dedup_by_book([(old, "tid_old"), (new, "tid_new")])
        assert len(winners) == 1
        assert winners[0][0]["_record_id"] == "r2"
        assert len(dropped) == 1
        assert dropped[0]["title"] == "某书"
        assert dropped[0]["kept_from"] == "tid_new/r2"
        assert dropped[0]["dropped_from"] == "tid_old/r1"

    def test_normalized_title_groups_variants(self):
        a, _ = self._rec("r1", "2026-05-01T10:00:00", "《某书》")
        b, _ = self._rec("r2", "2026-05-18T10:00:00", "某书 ")
        winners, dropped, skipped = dedup_by_book([(a, "tid_a"), (b, "tid_b")])
        assert len(winners) == 1
        assert winners[0][0]["_record_id"] == "r2"

    def test_no_title_records_skipped(self):
        good, _ = self._rec("r1", "2026-05-01T10:00:00", "A")
        bad = {"_record_id": "r2", "_synced_at": "2026-05-01T10:00:00", "fields": {}}
        winners, dropped, skipped = dedup_by_book([(good, "tid_a"), (bad, "tid_b")])
        assert len(winners) == 1
        assert skipped == 1
        assert dropped == []
```

- [ ] **Step 10: 运行测试确认失败**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestDedupByBook -v`
Expected: `ImportError: cannot import name 'dedup_by_book'`

- [ ] **Step 11: 实现 dedup_by_book**

追加到 `book_dedup.py`：

```python
def dedup_by_book(
    records_with_table: list[tuple[dict, str]],
) -> tuple[list[tuple[dict, str]], list[dict], int]:
    """按归一化书名去重一组 (record, table_id) 二元组。

    Args:
        records_with_table: [(record_dict, table_id), ...]

    Returns:
        (winners, dropped_info, skipped_no_title)
        - winners: [(winner_record, winner_table_id), ...]
        - dropped_info: [{"title", "kept_from", "dropped_from"}, ...]
        - skipped_no_title: 没有 title 字段的 record 数（不进 dedup、不进 dropped）
    """
    groups: dict[str, list[tuple[dict, str]]] = {}
    skipped = 0
    for rec, tid in records_with_table:
        raw_title = _extract_record_title(rec)
        key = normalize_title(raw_title)
        if not key:
            skipped += 1
            continue
        groups.setdefault(key, []).append((rec, tid))

    winners: list[tuple[dict, str]] = []
    dropped_info: list[dict] = []
    for key, group in groups.items():
        if len(group) == 1:
            winners.append(group[0])
            continue
        records_only = [r for r, _ in group]
        winner_rec, _ = select_winner(records_only)
        winner_tid = next(tid for r, tid in group if r is winner_rec)
        winners.append((winner_rec, winner_tid))
        kept_from = f"{winner_tid}/{winner_rec.get('_record_id') or winner_rec.get('record_id', '')}"
        for r, tid in group:
            if r is winner_rec:
                continue
            dropped_from = f"{tid}/{r.get('_record_id') or r.get('record_id', '')}"
            dropped_info.append({
                "title": key,
                "kept_from": kept_from,
                "dropped_from": dropped_from,
            })

    return winners, dropped_info, skipped
```

- [ ] **Step 12: 运行所有 dedup 测试确认通过**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py -v`
Expected: 14 passed

- [ ] **Step 13: Commit**

```bash
git add script_rubric/feishu/book_dedup.py script_rubric/tests/test_book_dedup.py
git commit -m "$(cat <<'EOF'
feat(rubric): 飞书 bitable 书级去重纯函数模块

新建 book_dedup.py 含三个纯函数：normalize_title（归一化《》/空格），
select_winner（按 _synced_at 最大选 winner，tiebreak record_id 字典序），
dedup_by_book（按归一化 title 分组、每组取 winner、产出 dropped trace）。

14 个单测覆盖归一化、winner 选择、分组去重、空 title 跳过等场景。
全部为纯函数，下个 task 接入 rebuild_index。

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: rebuild_index 接入 dedup

**Files:**
- Modify: `script_rubric/feishu/record_store.py:177-200` (`rebuild_index` 函数)
- Test: `script_rubric/tests/test_book_dedup.py` (新增 `TestRebuildIndexDedup` 类)

- [ ] **Step 1: 写失败集成测试**

追加到 `test_book_dedup.py`：

```python
import json
from pathlib import Path

import pytest

from script_rubric.feishu.record_store import rebuild_index, save_record, save_table_meta


@pytest.fixture
def temp_records_root(tmp_path, monkeypatch):
    """临时 RECORDS_ROOT，避免污染真实数据。"""
    fake_root = tmp_path / "bitable_records"
    fake_root.mkdir()
    monkeypatch.setattr("script_rubric.feishu.record_store.RECORDS_ROOT", fake_root)
    return fake_root


def _write_record(root, table_id, table_name, record_id, title, synced_at, app_token="app_x"):
    """直接落盘一条 per-record 文件，绕过 sync 流程。"""
    tdir = root / table_id
    tdir.mkdir(exist_ok=True)
    meta = tdir / "_meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({
            "table_id": table_id,
            "table_name": table_name,
            "fields": [{"field_name": "书名"}],
            "_updated_at": synced_at,
            "_source_app_token": app_token,
        }, ensure_ascii=False), encoding="utf-8")
    rec_path = tdir / f"{record_id}.json"
    rec_path.write_text(json.dumps({
        "record_id": record_id,
        "fields": {"书名": title},
        "_record_id": record_id,
        "_synced_at": synced_at,
        "_source_app_token": app_token,
    }, ensure_ascii=False), encoding="utf-8")


class TestRebuildIndexDedup:
    def test_dedup_keeps_latest_across_table_ids(self, temp_records_root, tmp_path):
        # 同名书在两个 table_id 都出现（模拟两次副本拉取生成不同 table_id）
        _write_record(temp_records_root, "tid_old", "精品", "r1", "某书", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_new", "精品", "r2", "某书", "2026-05-18T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        # 索引里同表名应合并为 1 条 table 项，records 里只有 winner
        precision_tables = [t for t in index["tables"] if t["table_name"] == "精品"]
        assert len(precision_tables) == 1
        records = precision_tables[0]["records"]
        assert len(records) == 1
        assert records[0]["fields"]["书名"] == "某书"
        # winner 是 r2（_record_id 内部字段被清理；从原始 record_id 看）
        assert records[0]["record_id"] == "r2"

    def test_dedup_stats_emitted(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "A", "2026-05-18T10:00:00")
        _write_record(temp_records_root, "tid_c", "精品", "r3", "B", "2026-05-18T10:00:00")
        # 无 title 的脏记录
        tdir = temp_records_root / "tid_a"
        (tdir / "r_empty.json").write_text(json.dumps({
            "record_id": "r_empty", "fields": {},
            "_record_id": "r_empty", "_synced_at": "2026-05-01T10:00:00",
        }, ensure_ascii=False), encoding="utf-8")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        stats = index["_dedup_stats"]
        assert stats["unique_books"] == 2
        assert stats["dropped_duplicates"] == 1
        assert stats["skipped_no_title"] == 1
        assert stats["total_files"] == 4

        dropped = index["_dedup_dropped"]
        assert len(dropped) == 1
        assert dropped[0]["title"] == "A"

    def test_cross_table_winner_in_its_table_only(self, temp_records_root, tmp_path):
        # 同书在两张不同表，winner 在「精品」时，「冲量」中不应出现
        _write_record(temp_records_root, "tid_chong", "冲量", "r1", "某书", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_jing", "精品", "r2", "某书", "2026-05-18T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        chong = [t for t in index["tables"] if t["table_name"] == "冲量"][0]
        jing = [t for t in index["tables"] if t["table_name"] == "精品"][0]
        assert len(chong["records"]) == 0
        assert len(jing["records"]) == 1
        assert jing["records"][0]["record_id"] == "r2"

    def test_rebuild_idempotent_ignoring_timestamp(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-18T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "A", "2026-05-01T10:00:00")

        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        idx1 = rebuild_index(out1, latest_app_token="app_x")
        idx2 = rebuild_index(out2, latest_app_token="app_x")

        # 忽略 synced_at 头部时间戳后应完全一致
        for d in (idx1, idx2):
            d.pop("synced_at")
        assert idx1 == idx2

    def test_same_table_name_multiple_dirs_merged(self, temp_records_root, tmp_path):
        # 3 个 table_id 都叫「精品」，索引里应只有 1 条 table 项
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "B", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_c", "精品", "r3", "C", "2026-05-01T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        jing_tables = [t for t in index["tables"] if t["table_name"] == "精品"]
        assert len(jing_tables) == 1
        titles = sorted(r["fields"]["书名"] for r in jing_tables[0]["records"])
        assert titles == ["A", "B", "C"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestRebuildIndexDedup -v`
Expected: 失败（多种：`_dedup_stats` 键不存在、同表名多目录未合并、跨表 winner 未生效）

- [ ] **Step 3: 改造 rebuild_index**

替换 `script_rubric/feishu/record_store.py` 第 177-200 行（整个 `rebuild_index` 函数）为：

```python
def rebuild_index(out_path: Path, latest_app_token: str | None = None) -> dict:
    """从 per-record 文件并集 rebuild bitable_rubric.json 索引，并按书名去重。

    流程：
      1. 遍历所有 table_id 目录，按 table_name 分组
      2. 每张表内按归一化书名去重（最新 _synced_at 胜出）
      3. 同表名的多个 table_id 目录合并为单条 table 项
      4. 输出附加 _dedup_stats / _dedup_dropped 供审计

    Args:
        out_path: 索引文件输出路径
        latest_app_token: 本次同步的 app_token（写入索引头部用于溯源）
    """
    from script_rubric.feishu.book_dedup import dedup_by_book

    # Step 1: 收集所有 (record, table_id) 并按 table_name 分组
    by_table_name: dict[str, list[tuple[dict, str]]] = {}
    meta_by_table_name: dict[str, dict] = {}  # 取最近 _updated_at 的 meta
    total_files = 0

    for tid in sorted(list_table_ids()):
        meta = load_table_meta(tid)
        if meta is None:
            continue
        table_name = meta.get("table_name", "")
        if not table_name:
            continue
        # 选最近 _updated_at 的 meta 作为该 table_name 的代表
        existing_meta = meta_by_table_name.get(table_name)
        if existing_meta is None or (meta.get("_updated_at", "") > existing_meta.get("_updated_at", "")):
            meta_by_table_name[table_name] = meta

        for rid in list_record_ids(tid):
            rec = load_record(tid, rid)
            if rec is None:
                continue
            total_files += 1
            by_table_name.setdefault(table_name, []).append((rec, tid))

    # Step 2: 每张 table_name 内 dedup
    tables = []
    all_dropped: list[dict] = []
    unique_books = 0
    dropped_duplicates = 0
    skipped_no_title = 0

    for table_name in sorted(by_table_name.keys()):
        records_with_tid = by_table_name[table_name]
        winners, dropped, skipped = dedup_by_book(records_with_tid)
        unique_books += len(winners)
        dropped_duplicates += len(dropped)
        skipped_no_title += skipped
        all_dropped.extend(dropped)

        # 清理 winner 内部元数据，附加 _last_source
        cleaned_records = []
        for rec, source_tid in winners:
            clean = {k: v for k, v in rec.items() if not k.startswith("_")}
            if "record_id" not in clean and "_record_id" in rec:
                clean["record_id"] = rec["_record_id"]
            if "id" not in clean and rec.get("_record_id"):
                clean["id"] = rec["_record_id"]
            clean["_last_source"] = {
                "app_token": rec.get("_source_app_token", ""),
                "table_id": source_tid,
                "record_id": rec.get("_record_id") or rec.get("record_id", ""),
                "synced_at": rec.get("_synced_at", ""),
            }
            cleaned_records.append(clean)

        # winner 贡献最多的 table_id 作为该 table_name 的代表 id
        tid_count: dict[str, int] = {}
        for _, source_tid in winners:
            tid_count[source_tid] = tid_count.get(source_tid, 0) + 1
        representative_tid = max(tid_count.items(), key=lambda kv: (kv[1], kv[0]))[0] if tid_count else ""

        meta = meta_by_table_name[table_name]
        tables.append({
            "table_id": representative_tid or meta.get("table_id", ""),
            "table_name": table_name,
            "fields": meta.get("fields", []),
            "records": cleaned_records,
        })

    data = {
        "synced_at": datetime.now().isoformat(),
        "app_token": latest_app_token or "",
        "tables": tables,
        "_index_rebuilt_from": str(RECORDS_ROOT),
        "_dedup_stats": {
            "total_files": total_files,
            "unique_books": unique_books,
            "dropped_duplicates": dropped_duplicates,
            "skipped_no_title": skipped_no_title,
        },
        "_dedup_dropped": all_dropped,
    }
    _atomic_write_json(out_path, data)
    return data
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py -v`
Expected: 19 passed (14 + 5)

- [ ] **Step 5: 跑现有相关测试确认无回归**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_merge_bitable.py script_rubric/tests/test_match_texts.py -v`
Expected: all passed

- [ ] **Step 6: Commit**

```bash
git add script_rubric/feishu/record_store.py script_rubric/tests/test_book_dedup.py
git commit -m "$(cat <<'EOF'
feat(rubric): rebuild_index 接入书级去重

rebuild_index 现按 table_name 聚合所有 table_id 目录，每张表内
按归一化书名去重（最新 _synced_at 胜出），输出附加 _dedup_stats /
_dedup_dropped 供审计。winner record 内嵌 _last_source 标记来源。

per-record 原始文件完全不动；下游 parse_bitable 读 records 字段，
对新增的 _last_source / _dedup_* 不敏感，保持向后兼容。

5 个集成测试覆盖：跨 table_id dedup、stats 输出、跨表 winner
归属、rebuild 幂等、同表名多目录合并。

Constraint: 必须复用 dedup_by_book 纯函数（已 task 1 验证）
Confidence: high
Scope-risk: narrow
Directive: 不要把 dedup 逻辑下沉到 sync_table_records——sync 层
保持原样累积，dedup 仅在视图层

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: sync allowlist 改为不过滤

**Files:**
- Modify: `script_rubric/feishu/sync_bitable.py:55` (`EXPECTED_TABLES`) 和 `:85-86` (循环过滤)

- [ ] **Step 1: 写失败测试**

追加到 `test_book_dedup.py`：

```python
class TestFetchBitableAllowlistNone:
    """allowlist=None 时应拉所有表，不过滤。"""

    def test_none_allowlist_does_not_skip(self, monkeypatch):
        """模拟 list_bitable_tables 返回多张表，allowlist=None 时全部进 tables_data。"""
        from script_rubric.feishu import sync_bitable

        # mock 各依赖函数
        monkeypatch.setattr(sync_bitable, "get_tenant_access_token", lambda: "tok")
        monkeypatch.setattr(sync_bitable, "resolve_url_to_bitable_app_token", lambda u, t: "app_x")
        monkeypatch.setattr(sync_bitable, "list_bitable_tables", lambda t, a: [
            {"table_id": "tid_a", "name": "精品"},
            {"table_id": "tid_b", "name": "冲量"},
            {"table_id": "tid_c", "name": "内部本"},
            {"table_id": "tid_d", "name": "成品表"},
        ])
        monkeypatch.setattr(sync_bitable, "list_bitable_fields", lambda t, a, tid: [
            {"field_name": "书名"}
        ])
        monkeypatch.setattr(sync_bitable, "fetch_all_bitable_records", lambda t, a, tid: [
            {"record_id": f"r_{tid}", "fields": {"书名": f"书{tid}"}}
        ])

        result = sync_bitable.fetch_bitable("https://x/base/app_x", tables_allowlist=None)

        table_names = sorted(t["table_name"] for t in result["tables"])
        assert table_names == ["内部本", "冲量", "成品表", "精品"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestFetchBitableAllowlistNone -v`
Expected: 失败 — 当前 `EXPECTED_TABLES = {"冲量", "精品"}`，"内部本"和"成品表"会被跳过

- [ ] **Step 3: 改 EXPECTED_TABLES**

`script_rubric/feishu/sync_bitable.py` 第 55 行：

```python
EXPECTED_TABLES = None  # None = 拉全部表；per-source `tables` 字段仍可显式限制
```

- [ ] **Step 4: 改 fetch_bitable 内部过滤逻辑**

`script_rubric/feishu/sync_bitable.py` 第 76 行（`allowlist = ...`）和第 85-86 行（`if table_name not in allowlist`）：

把：
```python
    allowlist = tables_allowlist if tables_allowlist is not None else EXPECTED_TABLES
```
改成：
```python
    allowlist = tables_allowlist if tables_allowlist is not None else EXPECTED_TABLES
    # allowlist 现在可以是 None（不过滤）或 set（白名单）
```

把：
```python
        if table_name not in allowlist:
            print(f"  跳过表「{table_name}」（不在 allowlist {sorted(allowlist)}）")
            continue
```
改成：
```python
        if allowlist is not None and table_name not in allowlist:
            print(f"  跳过表「{table_name}」（不在 allowlist {sorted(allowlist)}）")
            continue
```

同时更新 docstring。把第 70-72 行：
```python
        tables_allowlist: 只拉取这些表名；None 时回退到 EXPECTED_TABLES。
            注意：高级权限模式下，list_tables 可能"假成功"返回空数组，
            此时 allowlist 不会触发任何拉取；调用方应检查 RuntimeError 提示。
```
改成：
```python
        tables_allowlist: 只拉取这些表名；None 时回退到 EXPECTED_TABLES
            （后者默认为 None = 不过滤、拉全部表）。
            注意：高级权限模式下，list_tables 可能"假成功"返回空数组，
            此时即便 allowlist=None 也无任何记录可拉；调用方应检查 RuntimeError 提示。
```

同时修复第 119-125 行的 RuntimeError 消息（避免 `sorted(None)` 报错）：

把：
```python
    if not tables_data:
        raise RuntimeError(
            f"未找到任何有效数据表（allowlist={sorted(allowlist)}）。"
            f"实际表名: {[t.get('name') for t in tables_meta]}。"
            f"如果 list_tables 返回空数组，多半是 base 开启了高级权限但未给当前 app 配权 "
            f"（症状：app_info 200、list_tables 200 items=[]、list_fields 403 code=1254302）。"
        )
```
改成：
```python
    if not tables_data:
        allowlist_repr = sorted(allowlist) if allowlist is not None else "<全部>"
        raise RuntimeError(
            f"未找到任何有效数据表（allowlist={allowlist_repr}）。"
            f"实际表名: {[t.get('name') for t in tables_meta]}。"
            f"如果 list_tables 返回空数组，多半是 base 开启了高级权限但未给当前 app 配权 "
            f"（症状：app_info 200、list_tables 200 items=[]、list_fields 403 code=1254302）。"
        )
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/tests/test_book_dedup.py::TestFetchBitableAllowlistNone -v`
Expected: 1 passed

- [ ] **Step 6: 跑全部测试确认无回归**

Run: `cd /data/project/novel-writer && python3 -m pytest script_rubric/ -v`
Expected: all passed

- [ ] **Step 7: Commit**

```bash
git add script_rubric/feishu/sync_bitable.py script_rubric/tests/test_book_dedup.py
git commit -m "$(cat <<'EOF'
feat(rubric): sync 层 allowlist 默认改为不过滤

EXPECTED_TABLES = None（拉全部表），配合书级去重让任何被复制进来的
副本都能完整本地化。per-source 的 tables 字段仍然生效，保留显式限制
能力作未来兜底。

fetch_bitable 内部过滤逻辑 + RuntimeError 消息兼容 allowlist=None。

下游 parse_bitable.EXPECTED_TABLES = {精品, 冲量} 不动（评分管线本来
就只跑这两张表，内部本无评分；两层 allowlist 职责独立）。

Constraint: 不能改下游 parse_bitable.EXPECTED_TABLES（评分管线稳定）
Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 现网数据验收

**Files:** 无修改 — 在现有 7 个 table_id 目录上跑一次 rebuild_index、人工验证

- [ ] **Step 1: 备份当前 bitable_rubric.json**

```bash
cd /data/project/novel-writer
cp script_rubric/data/bitable_rubric.json script_rubric/data/bitable_rubric.before-dedup.json
```

- [ ] **Step 2: 跑 rebuild_index over 现有 7 个目录**

```bash
cd /data/project/novel-writer
python3 -c "
from pathlib import Path
from script_rubric.feishu.record_store import rebuild_index
out = Path('script_rubric/data/bitable_rubric.json')
data = rebuild_index(out, latest_app_token='dedup-rebuild')
print('--- _dedup_stats ---')
print(data['_dedup_stats'])
print('--- tables summary ---')
for t in data['tables']:
    print(f'  {t[\"table_name\"]:8} records={len(t[\"records\"])} table_id={t[\"table_id\"]}')
print(f'--- _dedup_dropped (front 10) ---')
for d in data['_dedup_dropped'][:10]:
    print(f'  {d}')
print(f'... total dropped: {len(data[\"_dedup_dropped\"])}')
"
```

Expected: 
- `_dedup_stats.total_files` ≈ 207（与最近一次 multi-source 同步记录的 total_records 一致）
- `_dedup_stats.unique_books` < total_files（有重复才算改造生效）
- `_dedup_stats.dropped_duplicates` = total_files - unique_books - skipped_no_title
- tables 数量 = 3（精品 / 冲量 / 内部本，从原本的 7 个 table_id 合并）

- [ ] **Step 3: 人工对比前后**

```bash
cd /data/project/novel-writer
python3 -c "
import json
before = json.load(open('script_rubric/data/bitable_rubric.before-dedup.json'))
after = json.load(open('script_rubric/data/bitable_rubric.json'))
print('=== BEFORE ===')
for t in before['tables']:
    print(f'  {t[\"table_name\"]:8} records={len(t[\"records\"])}')
print(f'  total: {sum(len(t[\"records\"]) for t in before[\"tables\"])}')
print('=== AFTER ===')
for t in after['tables']:
    print(f'  {t[\"table_name\"]:8} records={len(t[\"records\"])}')
print(f'  total: {sum(len(t[\"records\"]) for t in after[\"tables\"])}')
print(f'  reduction: {sum(len(t[\"records\"]) for t in before[\"tables\"]) - sum(len(t[\"records\"]) for t in after[\"tables\"])} 条重复消除')
"
```

Expected: after 的总数 < before；reduction > 0 即说明去重生效

- [ ] **Step 4: 抽查 1-2 本已知重复书**

```bash
cd /data/project/novel-writer
python3 -c "
import json
after = json.load(open('script_rubric/data/bitable_rubric.json'))
# 抽查 _dedup_dropped 里的前 3 本被淘汰的书，确认在 index 里只剩 1 条
for d in after['_dedup_dropped'][:3]:
    title = d['title']
    print(f'=== 抽查《{title}》（应只剩 1 条） ===')
    print(f'  kept_from={d[\"kept_from\"]} dropped_from={d[\"dropped_from\"]}')
    count = 0
    for t in after['tables']:
        for r in t['records']:
            book_name = (r.get('fields', {}).get('书名') or r.get('fields', {}).get('文本') or '').strip().strip('《》')
            if book_name == title:
                count += 1
                ls = r.get('_last_source', {})
                print(f'  -> 表「{t[\"table_name\"]}」 _last_source={ls}')
    assert count == 1, f'{title} 在索引里出现了 {count} 次'
    print('  ✓ 唯一')
"
```

Expected: 每本抽查的书在 index 里只出现 1 次，`_last_source` 指向最新副本

- [ ] **Step 5: 如果验收通过，删除备份**

```bash
cd /data/project/novel-writer
rm script_rubric/data/bitable_rubric.before-dedup.json
```

如果验收失败：保留备份，不要 commit，回到 Task 2 排查。

- [ ] **Step 6: 提交新 bitable_rubric.json**

```bash
cd /data/project/novel-writer
git add script_rubric/data/bitable_rubric.json
git commit -m "$(cat <<'EOF'
chore(rubric): 在历史累积数据上跑一次 dedup rebuild

对现有 7 个 table_id 目录（来自 3 个 app_token 副本）跑 rebuild_index，
按书名去重。total_files / unique_books / dropped_duplicates 见 _dedup_stats。

per-record 原始文件保留作 audit trail，未做物理清理。

Confidence: high
Scope-risk: narrow

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 结果

**1. Spec 覆盖：**
- ✅ §架构变化点 1 (EXPECTED_TABLES = None) → Task 3
- ✅ §架构变化点 2 (rebuild_index dedup) → Task 2
- ✅ §架构变化点 3 (per-record 不动) → 全程未触及 sync_table_records
- ✅ §Dedup 逻辑 6 步流程 → Task 1+2 (dedup_by_book + rebuild_index)
- ✅ §输出 schema (`_last_source`, `_dedup_stats`, `_dedup_dropped`, 同表名合并) → Task 2 step 3
- ✅ §错误处理 7 种情形 → 全部在 Task 1/2/3 测试里有对应 case
- ✅ §测试 9 项 → 14 单测 + 5 集成测试 + Task 4 人工验收
- ✅ §回滚路径 → Task 4 step 1 备份

**2. Placeholder 扫描：** 无 TBD / TODO / "implement later" / "similar to Task N"。

**3. 类型一致性：** `select_winner` / `dedup_by_book` / `normalize_title` 签名在 Task 1 定义、Task 2 调用一致；`_last_source` 字段结构在 spec 与 Task 2 step 3 一致。

**4. 已知预留：** Task 4 的 expected total_files = 207 是基于 sync_history.json 最近一次 multi-source 总和的估算，实际跑出来如果偏差不大（±20）就算正常；若严重偏离再排查（可能有未列入 sync_history 的副本目录）。
