from __future__ import annotations

import json
import logging
import statistics
from collections import defaultdict
from datetime import datetime

from script_rubric.config import (
    HANDBOOK_DIR, PROMPT_DIR, DIMENSION_KEYS, DIMENSION_NAMES_ZH, MODEL,
)
from script_rubric.models import ScriptArchive
from script_rubric.pipeline.llm_client import get_client, call_llm

logger = logging.getLogger(__name__)


def _summarize_archive(archive: ScriptArchive) -> str:
    dim_scores = ", ".join(
        f"{DIMENSION_NAMES_ZH.get(k, k)}{archive.dimensions[k].score}"
        for k in DIMENSION_KEYS
        if k in archive.dimensions
    )
    consensus = "; ".join(archive.consensus_points[:3]) if archive.consensus_points else "无"
    disagreement = "; ".join(archive.disagreement_points[:2]) if archive.disagreement_points else "无"
    return (
        f"### {archive.title} | {archive.genre} | {archive.status} | 均分 {archive.mean_score}\n"
        f"维度分: {dim_scores}\n"
        f"共识: {consensus}\n"
        f"分歧: {disagreement}\n"
    )


def _full_archive_text(archive: ScriptArchive) -> str:
    return json.dumps(archive.model_dump(), ensure_ascii=False, indent=1)


async def synthesize_universal(archives: list[ScriptArchive]) -> str:
    system_prompt = (PROMPT_DIR / "pass2_universal.md").read_text(encoding="utf-8")
    summaries = "\n".join(_summarize_archive(a) for a in archives)
    user_prompt = f"## 档案摘要（{len(archives)} 部）\n\n{summaries}"

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


async def synthesize_overlay(archives: list[ScriptArchive], genre: str) -> str:
    template = (PROMPT_DIR / "pass2_overlay.md").read_text(encoding="utf-8")
    system_prompt = template.replace("{genre}", genre)
    details = "\n\n".join(_full_archive_text(a) for a in archives)
    user_prompt = f"## {genre} 档案（{len(archives)} 部）\n\n{details}"

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


async def synthesize_redflags(
    rejected: list[ScriptArchive],
    borderline: list[ScriptArchive],
) -> str:
    system_prompt = (PROMPT_DIR / "pass2_redflags.md").read_text(encoding="utf-8")
    rej_text = "\n\n".join(_full_archive_text(a) for a in rejected)
    bord_text = "\n\n".join(_full_archive_text(a) for a in borderline)
    user_prompt = (
        f"## 被拒剧本（{len(rejected)} 部）\n\n{rej_text}\n\n"
        f"## 待改剧本（{len(borderline)} 部，供对比）\n\n{bord_text}"
    )

    client = get_client()
    return await call_llm(client, system_prompt, user_prompt, max_retries=2)


def _select_anchor(group: list[ScriptArchive], target_mean: float) -> ScriptArchive:
    return min(group, key=lambda a: (abs(a.mean_score - target_mean), a.title))


def _build_calibration_section(archives: list[ScriptArchive]) -> str:
    by_status: dict[str, list[ScriptArchive]] = defaultdict(list)
    for a in archives:
        by_status[a.status].append(a)

    status_order = ["签", "改", "拒"]
    rows = []
    status_stats: dict[str, dict] = {}

    for status in status_order:
        group = by_status.get(status, [])
        if not group:
            continue
        scores = [a.mean_score for a in group]
        mean = round(sum(scores) / len(scores), 1)
        if len(scores) >= 4:
            quartiles = statistics.quantiles(scores, n=4)
            p25, p75 = round(quartiles[0], 1), round(quartiles[2], 1)
        else:
            p25, p75 = round(min(scores), 1), round(max(scores), 1)

        dim_avgs = []
        for key in DIMENSION_KEYS:
            ds = [a.dimensions[key].score for a in group if key in a.dimensions]
            if ds:
                dim_avgs.append(f"{DIMENSION_NAMES_ZH.get(key, key)} {round(sum(ds)/len(ds), 1)}")
        dim_str = " / ".join(dim_avgs)

        rows.append(f"| {status} | {len(group)} | {mean} | {p25} | {p75} | {dim_str} |")
        status_stats[status] = {"mean": mean, "p25": p25, "p75": p75}

    table = (
        "### A. 状态-分数分布表\n\n"
        "| 状态 | 样本数 | 均分 | P25 | P75 | 维度典型分布 |\n"
        "|------|--------|------|-----|-----|--------------|\n"
        + "\n".join(rows)
    )

    threshold_lines = ["", "### B. 推荐阈值（advisory）", ""]
    if "签" in status_stats and "改" in status_stats:
        cut1 = round((status_stats["签"]["mean"] + status_stats["改"]["mean"]) / 2, 1)
        overlap_lo = min(status_stats["签"]["p25"], status_stats["改"]["p75"])
        overlap_hi = max(status_stats["签"]["p25"], status_stats["改"]["p75"])
        threshold_lines.append(
            f"- 签 / 改 边界 ≈ {cut1}（重叠区 {overlap_lo}-{overlap_hi} 需结合质性判断）"
        )
    if "改" in status_stats and "拒" in status_stats:
        cut2 = round((status_stats["改"]["mean"] + status_stats["拒"]["mean"]) / 2, 1)
        overlap_lo = min(status_stats["改"]["p25"], status_stats["拒"]["p75"])
        overlap_hi = max(status_stats["改"]["p25"], status_stats["拒"]["p75"])
        threshold_lines.append(
            f"- 改 / 拒 边界 ≈ {cut2}（重叠区 {overlap_lo}-{overlap_hi} 需结合质性判断）"
        )
    threshold_lines.append("")
    threshold_lines.append("> 分数与状态高度重叠，刻度仅为参考；最终 status 取决于质性维度（红旗/绿旗）。")

    anchor_lines = ["", "### C. 锚点剧本（每状态 1 部，按 mean_score 离均值最近选）", ""]
    for status in status_order:
        group = by_status.get(status, [])
        if not group:
            continue
        target = status_stats[status]["mean"]
        anchor = _select_anchor(group, target)
        dim_parts = [
            f"{DIMENSION_NAMES_ZH.get(k, k)} {anchor.dimensions[k].score}"
            for k in DIMENSION_KEYS
            if k in anchor.dimensions
        ]
        consensus = "；".join(anchor.consensus_points[:2]) if anchor.consensus_points else "无"
        if status == "签":
            flag_label, flag_items = "绿旗", anchor.green_flags[:1]
        else:
            flag_label, flag_items = "红旗", anchor.red_flags[:1]
        flag_text = "；".join(flag_items) if flag_items else "无"

        anchor_lines.append(f"#### 锚点 · {status} · 《{anchor.title}》")
        anchor_lines.append(f"- 类型：{anchor.genre} / 实际均分：{anchor.mean_score}")
        anchor_lines.append(f"- 维度：{' / '.join(dim_parts)}")
        anchor_lines.append(f"- 共识：{consensus}")
        anchor_lines.append(f"- {flag_label}：{flag_text}")
        anchor_lines.append("")

    return table + "\n" + "\n".join(threshold_lines) + "\n" + "\n".join(anchor_lines)


def _build_data_overview(archives: list[ScriptArchive]) -> str:
    total = len(archives)
    by_status: dict[str, int] = defaultdict(int)
    by_genre: dict[str, int] = defaultdict(int)
    for a in archives:
        by_status[a.status] += 1
        by_genre[a.genre] += 1

    dim_avgs = {}
    for key in DIMENSION_KEYS:
        scores = [a.dimensions[key].score for a in archives if key in a.dimensions]
        if scores:
            dim_avgs[DIMENSION_NAMES_ZH.get(key, key)] = round(sum(scores) / len(scores), 1)

    lines = [
        f"- 总样本: {total} 部",
        "- 状态分布: " + ", ".join(f"{k} {v}" for k, v in sorted(by_status.items())),
        "- 类型分布: " + ", ".join(f"{k} {v}" for k, v in sorted(by_genre.items())),
        "- 各维度平均分:",
    ]
    for name, avg in dim_avgs.items():
        lines.append(f"  - {name}: {avg}")
    return "\n".join(lines)


async def synthesize_all(archives: list[ScriptArchive], version: int = 1) -> tuple[str, dict]:
    logger.info(f"Pass 2: synthesizing handbook v{version} from {len(archives)} archives")

    logger.info("Batch A: universal rules")
    universal = await synthesize_universal(archives)

    by_genre: dict[str, list[ScriptArchive]] = defaultdict(list)
    for a in archives:
        if a.genre:
            by_genre[a.genre].append(a)

    overlays = {}
    for genre, group in by_genre.items():
        if len(group) >= 3:
            logger.info(f"Batch B: overlay for {genre} ({len(group)} scripts)")
            overlays[genre] = await synthesize_overlay(group, genre)
        else:
            logger.warning(f"Skipping overlay for {genre}: only {len(group)} scripts")
            overlays[genre] = f"*{genre}类型仅有 {len(group)} 部样本，数据不足，暂不生成专项规律。*"

    rejected = [a for a in archives if a.status == "拒"]
    borderline = [a for a in archives if a.status == "改"]
    logger.info(f"Batch C: red flags ({len(rejected)} rejected, {len(borderline)} borderline)")
    redflags = await synthesize_redflags(rejected, borderline)

    now = datetime.now().strftime("%Y-%m-%d")
    handbook = f"""# 剧本评审手册 v{version}

> 基于 {len(archives)} 部剧本的评审数据提炼
> 生成日期: {now} | 模型: {MODEL}

---

## 第一部分：通用规律

{universal}

---

## 第二部分：类型专项

"""
    for genre, text in overlays.items():
        handbook += f"### {genre}\n\n{text}\n\n"

    handbook += f"""---

## 第三部分：地雷清单

{redflags}

---

## 第四部分：评分校准刻度

> 本节由训练集统计确定性生成，为预测时的刻度参考。

{_build_calibration_section(archives)}

---

## 附录：数据概览

{_build_data_overview(archives)}
"""

    rubric = _build_rubric(archives, version, now)

    HANDBOOK_DIR.mkdir(parents=True, exist_ok=True)
    handbook_path = HANDBOOK_DIR / f"handbook_v{version}.md"
    handbook_path.write_text(handbook, encoding="utf-8")
    logger.info(f"Saved: {handbook_path}")

    rubric_path = HANDBOOK_DIR / f"rubric_v{version}.json"
    rubric_path.write_text(json.dumps(rubric, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"Saved: {rubric_path}")

    return handbook, rubric


def _build_rubric(archives: list[ScriptArchive], version: int, date: str) -> dict:
    dim_stats = {}
    for key in DIMENSION_KEYS:
        scores_by_status: dict[str, list[int]] = defaultdict(list)
        for a in archives:
            if key in a.dimensions:
                scores_by_status[a.status].append(a.dimensions[key].score)

        all_scores = [s for lst in scores_by_status.values() for s in lst]
        avg = round(sum(all_scores) / len(all_scores), 1) if all_scores else 0

        red_flags: set[str] = set()
        green_flags: set[str] = set()
        for a in archives:
            if key in a.dimensions:
                if a.status == "拒":
                    red_flags.update(a.red_flags)
                elif a.status == "签":
                    green_flags.update(a.green_flags)

        dim_stats[key] = {
            "name_zh": DIMENSION_NAMES_ZH.get(key, key),
            "avg_score": avg,
            "avg_by_status": {
                status: round(sum(scores) / len(scores), 1) if scores else None
                for status, scores in scores_by_status.items()
            },
            "red_flags_sample": list(red_flags)[:5],
            "green_flags_sample": list(green_flags)[:5],
        }

    by_genre: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for a in archives:
        for key in DIMENSION_KEYS:
            if key in a.dimensions:
                by_genre[a.genre][key].append(a.dimensions[key].score)

    type_overlays = {}
    for genre, dims in by_genre.items():
        type_overlays[genre] = {
            key: round(sum(scores) / len(scores), 1) if scores else None
            for key, scores in dims.items()
        }

    return {
        "version": str(version),
        "generated_at": date,
        "sample_size": len(archives),
        "universal_dimensions": dim_stats,
        "type_overlays": type_overlays,
    }
