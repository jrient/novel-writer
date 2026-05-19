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
