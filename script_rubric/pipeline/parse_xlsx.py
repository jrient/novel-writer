from __future__ import annotations

import json
from pathlib import Path

import openpyxl

from script_rubric.config import (
    XLSX_COLUMNS, REVIEWERS, MIN_SCORES_FOR_INCLUSION, SCORE_TIER_THRESHOLDS,
)
from script_rubric.models import Review, ScriptRecord


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


def parse_xlsx(path: Path, include_scored: bool = False) -> list[ScriptRecord]:
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.worksheets[0]

    records: list[ScriptRecord] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        title = _clean_str(row[XLSX_COLUMNS["title"]]) or ""
        if not title.strip():
            continue

        status = _clean_str(row[XLSX_COLUMNS["status"]])
        reviews = _extract_reviews(row)
        active_reviews = [r for r in reviews if r.score is not None or r.comment]

        if status and status in ("签", "改", "拒"):
            if not any(r.score is not None for r in reviews):
                continue
            records.append(ScriptRecord(
                title=title.strip(),
                source_type=_clean_str(row[XLSX_COLUMNS["source_type"]]) or "",
                genre=_clean_str(row[XLSX_COLUMNS["genre"]]) or "",
                submitter=_clean_str(row[XLSX_COLUMNS["submitter"]]) or "",
                status=status,
                status_source="confirmed",
                reviews=active_reviews,
            ))
        elif include_scored:
            inferred = _infer_status_from_scores(reviews)
            if inferred is None:
                continue
            records.append(ScriptRecord(
                title=title.strip(),
                source_type=_clean_str(row[XLSX_COLUMNS["source_type"]]) or "",
                genre=_clean_str(row[XLSX_COLUMNS["genre"]]) or "",
                submitter=_clean_str(row[XLSX_COLUMNS["submitter"]]) or "",
                status=inferred,
                status_source="score_inferred",
                reviews=active_reviews,
            ))

    return records


def _extract_reviews(row: tuple) -> list[Review]:
    reviews = []
    for name, score_col, comment_col in REVIEWERS:
        score_raw = row[score_col] if score_col < len(row) else None
        comment_raw = row[comment_col] if comment_col < len(row) else None

        score = _parse_score(score_raw)
        comment = _clean_str(comment_raw)

        if score is not None or comment:
            reviews.append(Review(reviewer=name, score=score, comment=comment))
    return reviews


def _parse_score(val) -> int | None:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        v = int(val)
        return v if 0 <= v <= 100 else None
    s = str(val).strip()
    if s.isdigit():
        v = int(s)
        return v if 0 <= v <= 100 else None
    return None


def _clean_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def save_parsed(records: list[ScriptRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = [r.model_dump() for r in records]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_parsed(path: Path) -> list[ScriptRecord]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [ScriptRecord.model_validate(d) for d in data]
