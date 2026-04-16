from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from datetime import datetime

from script_rubric.config import (
    BACKTEST_DIR, PROMPT_DIR, HANDBOOK_DIR,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.models import ScriptRecord, PredictResult, BacktestMetrics
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json

logger = logging.getLogger(__name__)


def split_holdout(
    records: list[ScriptRecord],
    ratio: float = 0.2,
    seed: int = 42,
) -> tuple[list[ScriptRecord], list[ScriptRecord]]:
    by_status: dict[str, list[ScriptRecord]] = defaultdict(list)
    for r in records:
        by_status[r.status].append(r)

    rng = random.Random(seed)
    train, test = [], []

    for _status, group in by_status.items():
        shuffled = group.copy()
        rng.shuffle(shuffled)
        n_test = max(1, round(len(shuffled) * ratio))
        test.extend(shuffled[:n_test])
        train.extend(shuffled[n_test:])

    return train, test


def evaluate_predictions(
    predictions: list[PredictResult],
    actuals: list[ScriptRecord],
) -> BacktestMetrics:
    actual_map = {r.title: r for r in actuals}
    details = []
    status_hits = 0
    range_hits = 0
    abs_errors = []
    critical_misses = 0
    total = 0

    for pred in predictions:
        actual = actual_map.get(pred.title)
        if not actual:
            continue

        total += 1
        status_hit = pred.predicted_status == actual.status
        if status_hit:
            status_hits += 1

        score_range = actual.score_range
        range_hit = False
        if score_range:
            range_hit = score_range[0] <= pred.predicted_score <= score_range[1]
            if range_hit:
                range_hits += 1

        mae = abs(pred.predicted_score - (actual.mean_score or 0))
        abs_errors.append(mae)

        is_critical = (
            (pred.predicted_status == "签" and actual.status == "拒")
            or (pred.predicted_status == "拒" and actual.status == "签")
        )
        if is_critical:
            critical_misses += 1

        details.append({
            "title": pred.title,
            "actual_status": actual.status,
            "predicted_status": pred.predicted_status,
            "status_hit": status_hit,
            "actual_mean": actual.mean_score,
            "actual_range": list(score_range) if score_range else None,
            "predicted_score": pred.predicted_score,
            "range_hit": range_hit,
            "mae": mae,
            "critical_miss": is_critical,
        })

    return BacktestMetrics(
        status_accuracy=status_hits / total if total else 0,
        range_accuracy=range_hits / total if total else 0,
        mae=sum(abs_errors) / len(abs_errors) if abs_errors else 0,
        critical_miss_rate=critical_misses / total if total else 0,
        total=total,
        details=details,
    )


async def predict_one(
    record: ScriptRecord,
    handbook_text: str,
) -> PredictResult | None:
    template = (PROMPT_DIR / "backtest_predict.md").read_text(encoding="utf-8")
    system_prompt = "你是一位使用评审手册的剧本评审员。严格按照 JSON 格式输出。"
    user_prompt = template.replace("{handbook}", handbook_text)
    user_prompt = user_prompt.replace("{title}", record.title)
    user_prompt = user_prompt.replace("{source_type}", record.source_type)
    user_prompt = user_prompt.replace("{genre}", record.genre)
    user_prompt = user_prompt.replace(
        "{text_content}",
        record.text_content[:30000] if record.text_content else "正文缺失",
    )

    client = get_client()
    try:
        raw = await call_llm(client, system_prompt, user_prompt, max_retries=2)
        data = extract_json(raw)
        return PredictResult.model_validate(data)
    except Exception as e:
        logger.error(f"Prediction failed for {record.title}: {e}")
        return None


async def run_backtest(
    test_records: list[ScriptRecord],
    version: int = 1,
) -> BacktestMetrics:
    handbook_path = HANDBOOK_DIR / f"handbook_v{version}.md"
    if not handbook_path.exists():
        raise FileNotFoundError(f"Handbook not found: {handbook_path}")

    handbook_text = handbook_path.read_text(encoding="utf-8")

    tasks = [predict_one(r, handbook_text) for r in test_records]
    results = await asyncio.gather(*tasks)
    predictions = [p for p in results if p is not None]

    metrics = evaluate_predictions(predictions, test_records)

    report = generate_report(metrics, version)
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    report_path = BACKTEST_DIR / f"report_v{version}.md"
    report_path.write_text(report, encoding="utf-8")
    logger.info(f"Backtest report saved: {report_path}")

    return metrics


def generate_report(metrics: BacktestMetrics, version: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    status_ok = "PASS" if metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY else "FAIL"
    range_ok = "PASS" if metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY else "FAIL"
    mae_ok = "PASS" if metrics.mae <= BACKTEST_MAE_THRESHOLD else "FAIL"
    crit_ok = "PASS" if metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE else "FAIL"

    lines = [
        f"# 回测报告 v{version}",
        f"> 生成时间: {now} | 测试集: {metrics.total} 部",
        "",
        "## 总览",
        f"- 状态命中率: {metrics.status_accuracy:.0%} [{status_ok}] (阈值 >={BACKTEST_STATUS_ACCURACY:.0%})",
        f"- 区间命中率: {metrics.range_accuracy:.0%} [{range_ok}] (阈值 >={BACKTEST_RANGE_ACCURACY:.0%})",
        f"- 分数 MAE: {metrics.mae:.1f} [{mae_ok}] (阈值 <={BACKTEST_MAE_THRESHOLD})",
        f"- 严重误判率: {metrics.critical_miss_rate:.0%} [{crit_ok}] (阈值 <={BACKTEST_CRITICAL_MISS_RATE:.0%})",
        "",
        "## 逐条明细",
        "| 剧本 | 实际状态 | 预测状态 | 实际均分 | 预测分 | 区间 | 命中 |",
        "|-------|---------|---------|---------|-------|------|------|",
    ]

    for d in metrics.details:
        range_str = f"[{d['actual_range'][0]},{d['actual_range'][1]}]" if d.get("actual_range") else "N/A"
        hit = "Y" if d["status_hit"] else "N"
        lines.append(
            f"| {d['title'][:20]} | {d['actual_status']} | {d['predicted_status']} "
            f"| {d['actual_mean']} | {d['predicted_score']} | {range_str} | {hit} |"
        )

    failures = [d for d in metrics.details if not d["status_hit"]]
    if failures:
        lines.append("")
        lines.append("## 失败案例分析")
        for d in failures:
            lines.append(f"### 《{d['title']}》预测\"{d['predicted_status']}\" 实际\"{d['actual_status']}\"")
            lines.append(f"- 预测分: {d['predicted_score']}, 实际均分: {d['actual_mean']}")
            if d.get("critical_miss"):
                lines.append("- **严重误判（签<->拒）**")
            lines.append("")

    all_pass = all([
        metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY,
        metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY,
        metrics.mae <= BACKTEST_MAE_THRESHOLD,
        metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE,
    ])

    lines.append("")
    lines.append("## 结论")
    if all_pass:
        lines.append(f"手册 v{version} **达标**，可用于 Phase 2。")
    else:
        lines.append(f"手册 v{version} **未达标**，建议分析失败案例后调整 prompt 重跑。")

    return "\n".join(lines)
