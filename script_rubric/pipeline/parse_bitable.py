"""
多维表格 JSON 解析模块
======================

将 sync_bitable.py 导出的 JSON 数据解析为 ScriptRecord/Review 模型。
自动发现评分人（根据「<人名>打分」「<人名>点评」字段对）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from script_rubric.models import Review, ScriptRecord
from script_rubric.config import MIN_SCORES_FOR_INCLUSION, SCORE_TIER_THRESHOLDS


EXPECTED_TABLES = {"冲量", "精品"}

# 必须存在的字段名（大小写不敏感）
REQUIRED_FIELD_NAMES = {"书名", "文本", "剧本名称", "剧本", "标题"}


def _normalize_field_name(name: str) -> str:
    """标准化字段名：去空格、统一大小写映射。"""
    return name.strip()


def _extract_reviewer_pairs(fields: list) -> list[tuple[str, str, str]]:
    """从字段列表自动发现评分人。

    匹配规则: 「<人名>打分」 + 「<人名>点评」 字段对。

    Returns:
        [(reviewer_name, score_field_name, comment_field_name), ...]
    """
    reviewers = []
    field_names = [_normalize_field_name(f["field_name"]) for f in fields]

    score_pattern = re.compile(r"^(.+?)打分$")
    comment_pattern = re.compile(r"^(.+?)点评$")

    score_fields = {}
    comment_fields = {}

    for name in field_names:
        m = score_pattern.match(name)
        if m:
            score_fields[m.group(1)] = name
        m = comment_pattern.match(name)
        if m:
            comment_fields[m.group(1)] = name

    for reviewer in score_fields:
        if reviewer in comment_fields:
            reviewers.append((reviewer, score_fields[reviewer], comment_fields[reviewer]))

    return reviewers


def _find_title_field(fields: list) -> str:
    """找到标题字段名。"""
    for f in fields:
        name = _normalize_field_name(f["field_name"])
        for required in REQUIRED_FIELD_NAMES:
            if required in name or name in required:
                return f["field_name"]
    raise ValueError(f"未找到标题字段，可用字段: {[f['field_name'] for f in fields]}")


def _find_field_by_name(fields: list, target: str) -> dict | None:
    """按名称模糊匹配字段定义。"""
    target_norm = _normalize_field_name(target)
    for f in fields:
        name_norm = _normalize_field_name(f["field_name"])
        if target_norm == name_norm or target in name_norm or name_norm in target:
            return f
    return None


def _get_cell_value(fields: list, record: dict, field_name: str) -> any:
    """从记录中提取指定字段的值。

    注意：bitable API 返回的 records.fields 使用 field_name 作为 key，
    而不是 field_id。因此直接按名称查找。
    """
    cells = record.get("fields", {})
    # 直接按字段名获取（优先）
    if field_name in cells:
        return cells[field_name]
    # Fallback: 模糊匹配
    field_def = _find_field_by_name(fields, field_name)
    if field_def:
        fid = field_def["field_id"]
        return cells.get(fid)
    return None


def _parse_score(val) -> int | None:
    """解析评分值。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        return v if 0 <= v <= 100 else None
    if isinstance(val, str):
        s = val.strip()
        if s.isdigit():
            v = int(s)
            return v if 0 <= v <= 100 else None
    return None


def _parse_text(val) -> str | None:
    """解析文本值。"""
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip()
        return s if s else None
    return str(val).strip() if val else None


def _parse_single_select(val) -> str | None:
    """解析单选值。"""
    if val is None:
        return None
    if isinstance(val, dict):
        return val.get("text") or val.get("name")
    if isinstance(val, str):
        return val.strip() if val.strip() else None
    return None


def _infer_status_from_scores(reviews: list[Review]) -> str | None:
    """根据评分均值推断状态分层。返回 None 表示评分不足。"""
    scores = [r.score for r in reviews if r.score is not None]
    if len(scores) < MIN_SCORES_FOR_INCLUSION:
        return None
    mean = sum(scores) / len(scores)
    if mean >= SCORE_TIER_THRESHOLDS["签"]:
        return "签"
    elif mean >= SCORE_TIER_THRESHOLDS["改"]:
        return "改"
    else:
        return "拒"


def parse_table(
    table_name: str,
    fields: list,
    records: list,
) -> list[ScriptRecord]:
    """解析单个表的记录。

    Args:
        table_name: 表名（用于校验）
        fields: 字段定义列表
        records: 记录列表

    Returns:
        ScriptRecord 列表

    Raises:
        ValueError: 表名不在 EXPECTED_TABLES，或未找到评分人/标题字段
    """
    if table_name not in EXPECTED_TABLES:
        raise ValueError(
            f"表名「{table_name}」不在预期集合 {EXPECTED_TABLES}，请确认 URL 是否正确"
        )

    reviewer_pairs = _extract_reviewer_pairs(fields)
    if not reviewer_pairs:
        raise ValueError(
            f"未发现评分人字段对（需同时有「<人名>打分」和「<人名>点评」），"
            f"可用字段: {[f['field_name'] for f in fields]}"
        )

    title_field_name = _find_title_field(fields)

    source_type_field = _find_field_by_name(fields, "来源类型") or _find_field_by_name(fields, "来源")
    genre_field = _find_field_by_name(fields, "题材分类") or _find_field_by_name(fields, "题材")
    submitter_field = _find_field_by_name(fields, "提交人")
    status_field = _find_field_by_name(fields, "状态")
    overall_score_field = _find_field_by_name(fields, "评分")

    out = []
    for rec in records:
        record_id = rec.get("record_id", "")
        title_raw = _get_cell_value(fields, rec, title_field_name)
        title = _parse_text(title_raw) or ""
        if not title.strip():
            continue

        source_type = _parse_text(_get_cell_value(fields, rec, source_type_field["field_name"] if source_type_field else ""))
        genre = _parse_text(_get_cell_value(fields, rec, genre_field["field_name"] if genre_field else ""))
        submitter = _parse_text(_get_cell_value(fields, rec, submitter_field["field_name"] if submitter_field else ""))
        status_raw = _parse_single_select(_get_cell_value(fields, rec, status_field["field_name"] if status_field else ""))
        overall_score = _parse_score(_get_cell_value(fields, rec, overall_score_field["field_name"] if overall_score_field else ""))

        reviews = []
        for reviewer_name, score_field, comment_field in reviewer_pairs:
            score = _parse_score(_get_cell_value(fields, rec, score_field))
            comment = _parse_text(_get_cell_value(fields, rec, comment_field))
            if score is not None or comment:
                reviews.append(Review(reviewer=reviewer_name, score=score, comment=comment))

        if not reviews:
            continue

        status_source = "confirmed"
        if status_raw and status_raw in ("签", "改", "拒"):
            status = status_raw
        else:
            inferred = _infer_status_from_scores(reviews)
            if inferred is None:
                continue
            status = inferred
            status_source = "score_inferred"

        out.append(ScriptRecord(
            title=title.strip(),
            source_type=source_type or "",
            genre=genre or "",
            submitter=submitter or "",
            status=status,
            status_source=status_source,
            reviews=reviews,
        ))

    return out


def parse_bitable_json(path: Path, include_scored: bool = True) -> list[ScriptRecord]:
    """从 sync_bitable 导出的 JSON 解析所有记录。

    Args:
        path: JSON 文件路径
        include_scored: 是否包含仅根据评分推断状态的记录

    Returns:
        ScriptRecord 列表
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    tables = data.get("tables", [])
    if not tables:
        raise ValueError(f"JSON 文件 {path} 无 tables 数据")

    all_records = []
    for tbl in tables:
        table_name = tbl.get("table_name", "")
        fields = tbl.get("fields", [])
        records = tbl.get("records", [])
        parsed = parse_table(table_name, fields, records)
        all_records.extend(parsed)

    return all_records