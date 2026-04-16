from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from script_rubric.config import (
    ARCHIVES_DIR, PROMPT_DIR, PASS1_MAX_RETRIES, DIMENSION_KEYS,
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
        if len(content) > 50000:
            content = content[:50000] + "\n\n[正文过长，已截断至前50000字]"
        parts.append(content)
    else:
        parts.append("正文缺失，仅基于元数据和评语分析。evidence_from_text 请留空。")

    return "\n".join(parts)


def _slug(title: str) -> str:
    return title.strip().replace(" ", "_").replace("/", "_")[:80]


def _archive_path(title: str) -> Path:
    return ARCHIVES_DIR / f"{_slug(title)}.json"


def _validate_archive(archive: ScriptArchive, record: ScriptRecord) -> list[str]:
    issues = []
    for key in DIMENSION_KEYS:
        if key not in archive.dimensions:
            issues.append(f"Missing dimension: {key}")
        else:
            dim = archive.dimensions[key]
            if not dim.evidence_from_reviews and record.reviews:
                issues.append(f"No review evidence for {key}")
    if archive.status != record.status:
        issues.append(f"Status mismatch: archive={archive.status}, record={record.status}")
    return issues


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
        )
        data = extract_json(raw)
        archive = ScriptArchive.model_validate(data)

        issues = _validate_archive(archive, record)
        if issues:
            logger.warning(f"Validation issues for {record.title}: {issues}")

        ARCHIVES_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
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
