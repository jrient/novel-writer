from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from script_rubric.config import (
    ARCHIVES_DIR, PROMPT_DIR, PASS1_MAX_RETRIES, DIMENSION_KEYS,
    PASS1_MAX_CONTENT_CHARS, PASS1_MAX_MISSING_DIMS_RATIO,
)
from script_rubric.models import ScriptRecord, ScriptArchive
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json

logger = logging.getLogger(__name__)


def _load_prompt() -> str:
    return (PROMPT_DIR / "pass1.md").read_text(encoding="utf-8")


def _build_user_prompt(record: ScriptRecord) -> str:
    parts = []
    parts.append("## 元数据")
    parts.append(f"标题: {record.title}")
    parts.append(f"类型: {record.source_type} / {record.genre}")
    if record.status_source == "score_inferred":
        parts.append(f"状态: 未确认（评分推断：{record.status}）")
    else:
        parts.append(f"状态: {record.status}")
    parts.append(f"提交人: {record.submitter}")
    parts.append(f"均分: {record.mean_score}")
    parts.append(f"分数区间: {record.score_range}")
    parts.append("")

    parts.append(f"## 责编评审 (共 {len(record.reviews)} 位)")
    for rev in record.reviews:
        score_str = str(rev.score) if rev.score is not None else "未打分"
        comment_str = rev.comment or "无评语"
        parts.append(f"【{rev.reviewer}】 分数: {score_str}")
        parts.append(f"评语: {comment_str}")
        parts.append("")

    parts.append("## 剧本正文")
    if record.text_content:
        content = record.text_content
        if len(content) > PASS1_MAX_CONTENT_CHARS:
            content = content[:PASS1_MAX_CONTENT_CHARS] + f"\n\n[正文过长，已截断至前{PASS1_MAX_CONTENT_CHARS}字]"
        parts.append(content)
    else:
        parts.append("正文缺失，仅基于元数据和评语分析。evidence_from_text 请留空。")

    return "\n".join(parts)


def _slug(title: str) -> str:
    return title.strip().replace(" ", "_").replace("/", "_")[:80]


def _archive_path(title: str) -> Path:
    return ARCHIVES_DIR / f"{_slug(title)}.json"


def _validate_archive(archive: ScriptArchive, record: ScriptRecord) -> tuple[list[str], list[str]]:
    """验证 archive 质量，返回 (critical_issues, warnings)。

    critical_issues: 严重问题，应 reject 该 archive
    warnings: 轻微问题，可接受但需记录
    """
    critical = []
    warnings = []
    missing_dims = []
    for key in DIMENSION_KEYS:
        if key not in archive.dimensions:
            missing_dims.append(key)
        else:
            dim = archive.dimensions[key]
            if not dim.evidence_from_reviews and record.reviews:
                warnings.append(f"No review evidence for {key}")

    # 缺失维度比例超阈值视为严重
    if len(missing_dims) > len(DIMENSION_KEYS) * PASS1_MAX_MISSING_DIMS_RATIO:
        critical.append(f"Too many missing dimensions ({len(missing_dims)}/{len(DIMENSION_KEYS)}): {missing_dims}")
    elif missing_dims:
        warnings.append(f"Missing dimensions: {missing_dims}")

    # 确认状态的剧本 archive 状态不一致视为严重
    if record.status_source == "confirmed" and archive.status != record.status:
        critical.append(f"Status mismatch: archive={archive.status}, record={record.status}")

    return critical, warnings


async def extract_one(
    record: ScriptRecord,
    system_prompt: str,
    skip_existing: bool = True,
) -> ScriptArchive | None:
    path = _archive_path(record.title)
    if skip_existing and path.exists():
        logger.info(f"Skipping (exists): {record.title}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ScriptArchive.model_validate(data)

    client = get_client()
    user_prompt = _build_user_prompt(record)

    try:
        raw = await call_llm(
            client, system_prompt, user_prompt,
            max_retries=PASS1_MAX_RETRIES,
            max_tokens=8192,
        )
        data = extract_json(raw)
        archive = ScriptArchive.model_validate(data)
        # 传播 status_source，标记此 archive 的状态是确认的还是推断的
        archive.status_source = record.status_source

        critical, warnings = _validate_archive(archive, record)
        if warnings:
            logger.warning(f"Validation warnings for {record.title}: {warnings}")
        if critical:
            logger.error(f"Rejecting archive for {record.title}: {critical}")
            return None

        ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            archive.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(f"Extracted: {record.title}")
        return archive

    except Exception as e:
        logger.error(f"Failed to extract {record.title}: {e}")
        return None


async def extract_all(
    records: list[ScriptRecord],
    skip_existing: bool = True,
) -> list[ScriptArchive]:
    system_prompt = _load_prompt()
    tasks = [
        extract_one(record, system_prompt, skip_existing)
        for record in records
    ]
    results = await asyncio.gather(*tasks)
    archives = [a for a in results if a is not None]
    logger.info(f"Extracted {len(archives)}/{len(records)} archives")
    return archives


def load_all_archives() -> list[ScriptArchive]:
    archives = []
    if not ARCHIVES_DIR.exists():
        return archives
    for path in sorted(ARCHIVES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        archives.append(ScriptArchive.model_validate(data))
    return archives
