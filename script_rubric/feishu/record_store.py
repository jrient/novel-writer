"""
飞书记录的本地持久化层（per-record file store）
================================================

设计目标：源端（飞书 bitable）随时可能失效——记录被删、表被解散、权限被收回——
本地必须有一份完整可用的副本。因此所有同步操作都是**非破坏性**的：

- 同步只 add/update，不会删除已有记录文件（除非显式 prune）
- 每条记录独立成文件（record_id 为文件名），写入用 tmp+rename 原子
- 表 meta（fields/table_name）单独存放，schema 漂移时仍可加载历史记录
- bitable_rubric.json 退化为 read-optimized 派生索引，从 per-record 文件 rebuild

目录布局：
  script_rubric/data/bitable_records/
  ├── {table_id}/
  │   ├── _meta.json                # {table_id, table_name, fields, _updated_at, _source_app_token}
  │   └── {record_id}.json          # {fields, _record_id, _synced_at, _source_app_token}
  └── ...

bitable_rubric.json 的派生结构与之前完全兼容（synced_at/app_token/tables[]），
下游 parse_bitable_json 不需要任何改动。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# 路径锚点 — script_rubric/data/bitable_records/
BASE_DIR = Path(__file__).resolve().parent.parent
RECORDS_ROOT = BASE_DIR / "data" / "bitable_records"

META_FILENAME = "_meta.json"


def _table_dir(table_id: str) -> Path:
    return RECORDS_ROOT / table_id


def record_path(table_id: str, record_id: str) -> Path:
    return _table_dir(table_id) / f"{record_id}.json"


def meta_path(table_id: str) -> Path:
    return _table_dir(table_id) / META_FILENAME


def _atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def save_table_meta(
    table_id: str,
    table_name: str,
    fields: list,
    source_app_token: str | None = None,
) -> None:
    """落盘表的 meta 信息（fields + table_name）。每次同步覆盖最新。"""
    meta = {
        "table_id": table_id,
        "table_name": table_name,
        "fields": fields,
        "_updated_at": datetime.now().isoformat(),
        "_source_app_token": source_app_token or "",
    }
    _atomic_write_json(meta_path(table_id), meta)


def load_table_meta(table_id: str) -> dict | None:
    p = meta_path(table_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_record(
    record: dict,
    table_id: str,
    source_app_token: str | None = None,
) -> bool:
    """落盘一条记录。

    Args:
        record: 飞书 API 返回的原始记录 dict（含 record_id + fields）
        table_id: 所属表 id
        source_app_token: 来源 bitable app_token（溯源用）

    Returns:
        True if 新增, False if 已存在被更新（按内容是否变化判定）
    """
    record_id = record.get("record_id") or record.get("id")
    if not record_id:
        raise ValueError(f"record 缺少 record_id: {record}")

    payload = dict(record)
    payload["_record_id"] = record_id
    payload["_synced_at"] = datetime.now().isoformat()
    if source_app_token:
        payload["_source_app_token"] = source_app_token

    path = record_path(table_id, record_id)
    is_new = not path.exists()

    if not is_new:
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_fields = existing.get("fields")
            if existing_fields == record.get("fields"):
                # 内容未变，仅刷新 _synced_at（保留原溯源）
                pass
        except json.JSONDecodeError:
            pass

    _atomic_write_json(path, payload)
    return is_new


def list_record_ids(table_id: str) -> list[str]:
    d = _table_dir(table_id)
    if not d.exists():
        return []
    return [p.stem for p in d.glob("*.json") if p.name != META_FILENAME]


def list_table_ids() -> list[str]:
    if not RECORDS_ROOT.exists():
        return []
    return [p.name for p in RECORDS_ROOT.iterdir() if p.is_dir()]


def load_record(table_id: str, record_id: str) -> dict | None:
    p = record_path(table_id, record_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_table(table_id: str) -> dict | None:
    """加载单表的全部记录 + meta，返回 bitable_rubric.json tables[] 中的一项结构。"""
    meta = load_table_meta(table_id)
    if meta is None:
        return None
    records = []
    for rid in list_record_ids(table_id):
        rec = load_record(table_id, rid)
        if rec is None:
            continue
        # 移除内部元数据（_record_id/_synced_at/_source_app_token），只保留飞书原始结构
        clean = {k: v for k, v in rec.items() if not k.startswith("_")}
        if "record_id" not in clean and "_record_id" in rec:
            clean["record_id"] = rec["_record_id"]
        if "id" not in clean and rec.get("_record_id"):
            clean["id"] = rec["_record_id"]
        records.append(clean)
    return {
        "table_id": table_id,
        "table_name": meta.get("table_name", ""),
        "fields": meta.get("fields", []),
        "records": records,
    }


def rebuild_index(out_path: Path, latest_app_token: str | None = None) -> dict:
    """从 per-record 文件并集 rebuild 出 bitable_rubric.json 索引。

    Args:
        out_path: 索引文件输出路径
        latest_app_token: 本次同步的 app_token（写入索引头部用于溯源）

    Returns:
        写入的索引内容
    """
    tables = []
    for tid in sorted(list_table_ids()):
        loaded = load_table(tid)
        if loaded is not None:
            tables.append(loaded)

    data = {
        "synced_at": datetime.now().isoformat(),
        "app_token": latest_app_token or "",
        "tables": tables,
        "_index_rebuilt_from": str(RECORDS_ROOT),
    }
    _atomic_write_json(out_path, data)
    return data


def migrate_from_legacy(legacy_path: Path, source_app_token: str | None = None) -> dict:
    """把旧版 bitable_rubric.json（单一大文件）迁移到 per-record 存储。

    幂等：
    - 已存在的 record_id 文件不会被覆盖（保留更旧的 _synced_at 元数据）
    - 已存在的 table meta 不会被覆盖

    Returns:
        {"records_migrated": N, "tables_migrated": M, "skipped_existing": K}
    """
    stats = {"records_migrated": 0, "tables_migrated": 0, "skipped_existing": 0}
    if not legacy_path.exists():
        return stats
    try:
        data = json.loads(legacy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        logger.warning(f"legacy bitable_rubric.json 格式错误，跳过迁移: {e}")
        return stats

    legacy_app_token = data.get("app_token") or source_app_token or ""
    for tbl in data.get("tables", []):
        tid = tbl.get("table_id") or ""
        if not tid:
            continue
        # 写 meta（仅当不存在时，避免覆盖最新 schema）
        if load_table_meta(tid) is None:
            save_table_meta(tid, tbl.get("table_name", ""), tbl.get("fields", []), legacy_app_token)
            stats["tables_migrated"] += 1
        for rec in tbl.get("records", []):
            rid = rec.get("record_id") or rec.get("id")
            if not rid:
                continue
            p = record_path(tid, rid)
            if p.exists():
                stats["skipped_existing"] += 1
                continue
            save_record(rec, tid, source_app_token=legacy_app_token)
            stats["records_migrated"] += 1
    return stats


def sync_table_records(
    records: list,
    table_id: str,
    table_name: str,
    fields: list,
    source_app_token: str | None = None,
) -> dict:
    """把一次飞书拉取得到的整张表非破坏性落盘。

    - 写每条记录到 {table_id}/{record_id}.json（覆盖更新）
    - 写表 meta 到 {table_id}/_meta.json
    - 不删除本地已有但本次未拉到的 record（保留作为历史快照）

    Returns:
        {"new": N, "updated": M, "preserved": K}（preserved = 本地有但本次没拉到）
    """
    save_table_meta(table_id, table_name, fields, source_app_token)

    fetched_ids = set()
    new_count = 0
    updated_count = 0
    for rec in records:
        rid = rec.get("record_id") or rec.get("id")
        if not rid:
            continue
        fetched_ids.add(rid)
        is_new = save_record(rec, table_id, source_app_token=source_app_token)
        if is_new:
            new_count += 1
        else:
            updated_count += 1

    local_ids = set(list_record_ids(table_id))
    preserved = len(local_ids - fetched_ids)

    return {"new": new_count, "updated": updated_count, "preserved": preserved}
