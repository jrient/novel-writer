#!/usr/bin/env python3
"""
飞书多维表格同步 CLI
=====================

从用户提供的 bitable URL 拉取数据，标准化为 JSON，
供 script_rubric pipeline 消费。

用法:
  # 单源同步
  python -m script_rubric.feishu.sync_bitable <bitable_url> [--run-pipeline]

  # 多源管理
  python -m script_rubric.feishu.sync_bitable --add-source <url> [--name <name>]
  python -m script_rubric.feishu.sync_bitable --all [--run-pipeline]
  python -m script_rubric.feishu.sync_bitable --list-sources
  python -m script_rubric.feishu.sync_bitable --remove-source <name>

非破坏性持久化:
  数据真源是 script_rubric/data/bitable_records/{table_id}/{record_id}.json
  每条记录独立成文件；同步只 add/update，从不删除已有文件。
  bitable_rubric.json 是从 per-record 文件 rebuild 出的派生索引。
  即使飞书源端记录消失或权限被收回，本地数据仍完整可用。

凭证：仅从环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET 读取，未设置则报错。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from script_rubric.feishu.feishu_common import (
    extract_bitable_token,
    extract_segments_text,
    fetch_all_bitable_records,
    get_tenant_access_token,
    list_bitable_fields,
    list_bitable_tables,
)
from script_rubric.feishu.record_store import (
    migrate_from_legacy,
    rebuild_index,
    sync_table_records,
)

load_dotenv()

EXPECTED_TABLES = {"冲量", "精品"}

# 路径锚点
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = PROJECT_ROOT / "script_rubric" / "data" / "bitable_rubric.json"
HISTORY_PATH = PROJECT_ROOT / "script_rubric" / "data" / "sync_history.json"
SOURCES_PATH = PROJECT_ROOT / "data" / "bitables.json"


def fetch_bitable(url_or_token: str) -> dict:
    """拉取 bitable 所有数据表（仅返回，不写盘）。"""
    app_token = extract_bitable_token(url_or_token)
    token = get_tenant_access_token()

    tables_meta = list_bitable_tables(token, app_token)
    tables_data = []

    for tbl in tables_meta:
        table_id = tbl["table_id"]
        table_name = tbl.get("name", table_id)

        if table_name not in EXPECTED_TABLES:
            print(f"  跳过表「{table_name}」（不在预期集合）")
            continue

        print(f"  拉取表「{table_name}」...")
        fields = list_bitable_fields(token, app_token, table_id)
        records = fetch_all_bitable_records(token, app_token, table_id)

        # 过滤掉无 title 的空记录（占位/草稿行）
        filtered = []
        for rec in records:
            fields_map = rec.get("fields", {})
            has_title = any(
                extract_segments_text(fields_map.get(f))
                for f in ("书名", "文本", "剧本名称", "剧本", "标题")
            )
            if has_title:
                filtered.append(rec)
        skipped = len(records) - len(filtered)
        if skipped:
            print(
                f"    字段 {len(fields)} 个，记录 {len(records)} 条"
                f"（过滤空记录 {skipped} 条，保留 {len(filtered)} 条）"
            )
        else:
            print(f"    字段 {len(fields)} 个，记录 {len(filtered)} 条")

        tables_data.append({
            "table_id": table_id,
            "table_name": table_name,
            "fields": fields,
            "records": filtered,
        })

    if not tables_data:
        raise RuntimeError(
            f"未找到任何有效数据表（预期 {EXPECTED_TABLES}）。"
            f"请检查 URL 是否正确，或确认表格是否启用了高级权限。"
            f"实际表名: {[t.get('name') for t in tables_meta]}"
        )

    return {
        "synced_at": datetime.now().isoformat(),
        "app_token": app_token,
        "tables": tables_data,
    }


def persist_to_store(fetched: dict) -> dict:
    """把一次抓取得到的所有表非破坏性落入 per-record 存储。

    Returns:
        {table_name: {"new": N, "updated": M, "preserved": K}}
    """
    app_token = fetched.get("app_token", "")
    stats_by_table: dict[str, dict] = {}
    for tbl in fetched["tables"]:
        stats = sync_table_records(
            records=tbl["records"],
            table_id=tbl["table_id"],
            table_name=tbl["table_name"],
            fields=tbl["fields"],
            source_app_token=app_token,
        )
        stats_by_table[tbl["table_name"]] = stats
    return stats_by_table


def auto_migrate_legacy() -> None:
    """首次运行时把旧 bitable_rubric.json 一次性迁入 per-record 存储。"""
    from script_rubric.feishu.record_store import RECORDS_ROOT, list_table_ids
    if list_table_ids():
        return  # 已有 per-record 数据，跳过
    if not DEFAULT_OUT.exists():
        return
    print(f"[migrate] 检测到旧 bitable_rubric.json，迁移到 per-record 存储...")
    stats = migrate_from_legacy(DEFAULT_OUT)
    print(
        f"[migrate] 完成：迁移 {stats['records_migrated']} 条记录、"
        f"{stats['tables_migrated']} 张表 meta、跳过 {stats['skipped_existing']} 条已存在"
    )


def append_history(entry: dict, history_path: Path = HISTORY_PATH) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.append(entry)
    history_path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# === 多数据源管理 ===


def load_sources() -> dict:
    if SOURCES_PATH.exists():
        return json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return {"sources": []}


def save_sources(sources: dict) -> None:
    SOURCES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SOURCES_PATH.write_text(
        json.dumps(sources, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cmd_add_source(args):
    sources = load_sources()
    url = args.add_source
    name = args.name or f"source_{len(sources['sources']) + 1}"

    for s in sources["sources"]:
        if s["url"] == url:
            print(f"数据源已存在: {s['name']} ({s['url']})")
            return

    sources["sources"].append({
        "name": name,
        "url": url,
        "active": True,
    })
    save_sources(sources)
    print(f"已添加数据源: {name}")
    print(f"  URL: {url}")


def cmd_remove_source(args):
    sources = load_sources()
    name = args.remove_source
    before = len(sources["sources"])
    sources["sources"] = [s for s in sources["sources"] if s["name"] != name]
    if len(sources["sources"]) == before:
        print(f"未找到数据源: {name}")
    else:
        save_sources(sources)
        print(f"已移除数据源: {name}")


def cmd_list_sources(args):
    sources = load_sources()
    if not sources["sources"]:
        print("没有配置数据源")
        return
    for s in sources["sources"]:
        status = "active" if s.get("active", True) else "inactive"
        print(f"  [{status}] {s['name']}: {s['url']}")


def cmd_sync_all(args):
    sources = load_sources()
    active_sources = [s for s in sources["sources"] if s.get("active", True)]
    if not active_sources:
        print("没有 active 的数据源，请先用 --add-source 添加")
        return

    auto_migrate_legacy()

    print(f"=== 多源同步 ===")
    print(f"数据源: {len(active_sources)} 个")
    print(f"索引输出: {DEFAULT_OUT}")
    print(f"持久化目录: {DEFAULT_OUT.parent / 'bitable_records'}")

    last_app_token = ""
    succeeded = []
    for src in active_sources:
        print(f"\n--- 拉取: {src['name']} ---")
        t0 = time.time()
        try:
            data = fetch_bitable(src["url"])
        except Exception as e:
            print(f"  拉取失败（本地数据保留不变）: {e}")
            continue

        elapsed = time.time() - t0
        last_app_token = data["app_token"]
        succeeded.append(src["name"])
        stats_by_table = persist_to_store(data)
        for tname, s in stats_by_table.items():
            print(
                f"  [{tname}] 新增 {s['new']} 条, 更新 {s['updated']} 条, "
                f"本地保留（源端未拉到）{s['preserved']} 条"
            )
        print(f"  拉取耗时: {elapsed:.1f}s")

    print(f"\n[index] 从 per-record 文件 rebuild 索引...")
    index = rebuild_index(DEFAULT_OUT, latest_app_token=last_app_token)
    final_total = sum(len(t["records"]) for t in index["tables"])
    print(f"已保存: {DEFAULT_OUT}（共 {final_total} 条）")

    append_history({
        "synced_at": index["synced_at"],
        "app_token": last_app_token,
        "mode": "multi_source",
        "sources_tried": [s["name"] for s in active_sources],
        "sources_succeeded": succeeded,
        "tables": [
            {"table_name": t["table_name"], "records": len(t["records"])}
            for t in index["tables"]
        ],
        "total_records": final_total,
    })

    if args.run_pipeline:
        print("\n触发 pipeline...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "script_rubric.pipeline.run", "incremental"],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            print(f"pipeline 执行失败 (code={result.returncode})")
            sys.exit(result.returncode)
        print("pipeline 执行完成")


def main():
    parser = argparse.ArgumentParser(description="飞书多维表格同步 CLI")
    parser.add_argument("url", nargs="?", help="多维表格 URL 或 app_token（单源模式）")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="输出 JSON 路径")
    parser.add_argument("--run-pipeline", action="store_true", help="同步后触发 pipeline")

    parser.add_argument("--add-source", help="添加数据源（需提供 URL）")
    parser.add_argument("--name", help="数据源名称（与 --add-source 配合使用）")
    parser.add_argument("--remove-source", help="移除指定名称的数据源")
    parser.add_argument("--list-sources", action="store_true", help="列出所有数据源")
    parser.add_argument("--all", action="store_true", help="拉取并合并所有 active 数据源")

    args = parser.parse_args()

    if args.list_sources:
        cmd_list_sources(args)
        return
    if args.add_source:
        cmd_add_source(args)
        return
    if args.remove_source:
        cmd_remove_source(args)
        return
    if args.all:
        cmd_sync_all(args)
        return

    if not args.url:
        parser.print_help()
        return

    auto_migrate_legacy()

    print(f"=== 飞书多维表格同步（单源） ===")
    print(f"URL: {args.url}")
    print(f"索引输出: {args.out}")

    t0 = time.time()
    data = fetch_bitable(args.url)
    elapsed_fetch = time.time() - t0
    print(f"拉取耗时: {elapsed_fetch:.1f}s")

    stats_by_table = persist_to_store(data)
    for tname, s in stats_by_table.items():
        print(
            f"  [{tname}] 新增 {s['new']} 条, 更新 {s['updated']} 条, "
            f"本地保留（源端未拉到）{s['preserved']} 条"
        )

    print(f"\n[index] 从 per-record 文件 rebuild 索引...")
    index = rebuild_index(args.out, latest_app_token=data["app_token"])
    final_total = sum(len(t["records"]) for t in index["tables"])
    print(f"已保存: {args.out}（共 {final_total} 条）")

    entry = {
        "synced_at": index["synced_at"],
        "app_token": data["app_token"],
        "mode": "single_source",
        "tables": [
            {"table_name": t["table_name"], "records": len(t["records"])}
            for t in index["tables"]
        ],
        "elapsed_fetch": elapsed_fetch,
        "total_records": final_total,
    }
    append_history(entry)
    print(f"历史已追加: {HISTORY_PATH}")

    if args.run_pipeline:
        print("\n触发 pipeline...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "script_rubric.pipeline.run", "incremental"],
            cwd=PROJECT_ROOT,
        )
        if result.returncode != 0:
            print(f"pipeline 执行失败 (code={result.returncode})")
            sys.exit(result.returncode)
        print("pipeline 执行完成")

    print(f"\n同步完成，总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
