#!/usr/bin/env python3
"""
飞书多维表格同步 CLI
=====================

从用户提供的 bitable URL 拉取数据，标准化为 JSON，
供 script_rubric pipeline 消费。

用法:
  # 单源同步
  python -m script_rubric.feishu.sync_bitable <bitable_url> [--out <path>] [--run-pipeline]

  # 多源管理
  python -m script_rubric.feishu.sync_bitable --add-source <url> [--name <name>]
  python -m script_rubric.feishu.sync_bitable --all [--run-pipeline]
  python -m script_rubric.feishu.sync_bitable --list-sources
  python -m script_rubric.feishu.sync_bitable --remove-source <name>

输出 JSON 结构:
  {
    "synced_at": "...",
    "app_token": "...",
    "tables": [
      {
        "table_id": "...",
        "table_name": "精品",
        "fields": [...],
        "records": [...]
      }
    ]
  }

凭证：仅从环境变量 FEISHU_APP_ID / FEISHU_APP_SECRET 读取，未设置则报错。
"""

from __future__ import annotations

import argparse
import json
import os
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
    merge_bitable_tables,
)

load_dotenv()

EXPECTED_TABLES = {"冲量", "精品"}

# 路径锚点
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_OUT = PROJECT_ROOT / "script_rubric" / "data" / "bitable_rubric.json"
HISTORY_PATH = PROJECT_ROOT / "script_rubric" / "data" / "sync_history.json"
SOURCES_PATH = PROJECT_ROOT / "data" / "bitables.json"
MERGE_HISTORY_PATH = PROJECT_ROOT / "data" / "merge_history.json"


def fetch_bitable(url_or_token: str) -> dict:
    """拉取 bitable 所有数据表。"""
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
        # 兼容 text_field_as_array 模式：title 字段可能是 str 或 list[segment]
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


def atomic_write(data: dict, path: Path) -> None:
    """原子写入 JSON 文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp_path, path)


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

    print(f"=== 多源同步 ===")
    print(f"数据源: {len(active_sources)} 个")
    print(f"输出: {DEFAULT_OUT}")

    existing_data = None
    if DEFAULT_OUT.exists():
        try:
            existing_data = json.loads(DEFAULT_OUT.read_text(encoding="utf-8"))
            old_total = sum(len(t["records"]) for t in existing_data.get("tables", []))
            print(f"已有数据: {old_total} 条")
        except (json.JSONDecodeError, Exception):
            print("已有数据格式错误，将重新生成")
            existing_data = None

    for src in active_sources:
        print(f"\n--- 拉取: {src['name']} ---")
        t0 = time.time()
        try:
            new_data = fetch_bitable(src["url"])
        except Exception as e:
            print(f"  拉取失败: {e}")
            continue

        elapsed = time.time() - t0
        new_total = sum(len(t["records"]) for t in new_data["tables"])
        print(f"  拉取耗时: {elapsed:.1f}s，共 {new_total} 条")

        if existing_data:
            merged_tables, stats = merge_bitable_tables(
                existing_data.get("tables", []),
                new_data["tables"],
            )
            existing_data["tables"] = merged_tables
            existing_data["synced_at"] = datetime.now().isoformat()
            existing_data["app_token"] = new_data["app_token"]
            print(
                f"  合并: 更新 {stats['updated']} 条, "
                f"追加 {stats['appended']} 条, 保留 {stats['retained']} 条"
            )

            append_merge_history({
                "merged_at": datetime.now().isoformat(),
                "source_name": src["name"],
                "app_token": new_data["app_token"],
                **stats,
                "total_after_merge": sum(len(t["records"]) for t in merged_tables),
            })
        else:
            existing_data = new_data
            print("  首次写入")

    if not existing_data:
        print("所有数据源拉取失败")
        return

    final_total = sum(len(t["records"]) for t in existing_data["tables"])
    atomic_write(existing_data, DEFAULT_OUT)
    print(f"\n已保存: {DEFAULT_OUT}（共 {final_total} 条）")

    append_history({
        "synced_at": existing_data["synced_at"],
        "app_token": existing_data["app_token"],
        "mode": "multi_source",
        "sources": [s["name"] for s in active_sources],
        "tables": [
            {"table_name": t["table_name"], "records": len(t["records"])}
            for t in existing_data["tables"]
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


def append_merge_history(entry: dict) -> None:
    MERGE_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    history = []
    if MERGE_HISTORY_PATH.exists():
        try:
            history = json.loads(MERGE_HISTORY_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            history = []
    history.append(entry)
    MERGE_HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


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

    print(f"=== 飞书多维表格同步 ===")
    print(f"URL: {args.url}")
    print(f"输出: {args.out}")

    t0 = time.time()
    data = fetch_bitable(args.url)
    elapsed_fetch = time.time() - t0
    print(f"拉取耗时: {elapsed_fetch:.1f}s")

    total_records = sum(len(t["records"]) for t in data["tables"])
    print(f"总记录: {total_records} 条")

    t1 = time.time()
    atomic_write(data, args.out)
    elapsed_write = time.time() - t1
    print(f"写入耗时: {elapsed_write:.1f}s")
    print(f"已保存: {args.out}")

    entry = {
        "synced_at": data["synced_at"],
        "app_token": data["app_token"],
        "mode": "single_source",
        "tables": [
            {"table_name": t["table_name"], "records": len(t["records"])}
            for t in data["tables"]
        ],
        "elapsed_fetch": elapsed_fetch,
        "elapsed_write": elapsed_write,
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
