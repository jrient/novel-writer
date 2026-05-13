"""
Holdout 评分（外部待审核剧本0508）→ handbook 最新版
========================================================

主输出 = 预测评分（0-100）；签/改/拒 仅作参考。
指标：
- 全样本预测分一览
- 按 actual_status 分组的分数分布（discrimination 体检）
- 对带真实均分的样本算 MAE / range hit

容错：predicted_score 若是 float（如 73.5），自动 round 进 int，避免丢样本。
"""

from __future__ import annotations

import asyncio
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from script_rubric.config import HANDBOOK_DIR, PROMPT_DIR
from script_rubric.feishu.feishu_common import (
    get_tenant_access_token,
    list_bitable_fields,
    fetch_all_bitable_records,
)
from script_rubric.pipeline.parse_bitable import parse_table
from script_rubric.pipeline.fetch_docx import fetch_many
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json
from script_rubric.models import PredictResult

APP_TOKEN = "IXbHb8BiuaCjutsu2eJcDBL6nCf"
TABLES = [
    ("tblLaAiHPjepItfL", "冲量"),
    ("tblYb5CVaK9C66O4", "精品"),
]
OUT_DIR = Path("/app/script_rubric/outputs/experiments")


def _latest_handbook_version() -> int:
    versions = []
    for p in HANDBOOK_DIR.glob("handbook_v*.md"):
        try:
            versions.append(int(p.stem.split("v")[-1]))
        except ValueError:
            continue
    return max(versions) if versions else 1


async def _predict_tolerant(record, handbook_text: str) -> PredictResult | None:
    """predict_one 的容错版：predicted_score 是 float 时 round 成 int，再交 pydantic 校验。"""
    template = (PROMPT_DIR / "backtest_predict.md").read_text(encoding="utf-8")
    user_prompt = (
        template
        .replace("{handbook}", handbook_text)
        .replace("{title}", record.title)
        .replace("{source_type}", record.source_type or "")
        .replace("{genre}", record.genre or "")
        .replace("{text_content}", (record.text_content or "正文缺失")[:30000])
    )
    system_prompt = "你是一位使用评审手册的剧本评审员。严格按照 JSON 格式输出。"

    client = get_client()
    try:
        raw = await call_llm(client, system_prompt, user_prompt, max_retries=2, temperature=0.0)
        data = extract_json(raw)
        if isinstance(data.get("predicted_score"), float):
            data["predicted_score"] = round(data["predicted_score"])
        # 维度分也可能是 float
        ds = data.get("dimension_scores")
        if isinstance(ds, dict):
            data["dimension_scores"] = {k: round(v) if isinstance(v, float) else v for k, v in ds.items()}
        return PredictResult.model_validate(data)
    except Exception as e:
        print(f"  [FAIL] {record.title[:30]}: {e}")
        return None


async def main():
    version = _latest_handbook_version()
    handbook_path = HANDBOOK_DIR / f"handbook_v{version}.md"
    handbook_text = handbook_path.read_text(encoding="utf-8")
    print(f"使用 handbook_v{version}")

    tok = get_tenant_access_token()

    all_records = []
    table_stats = {}
    for table_id, table_name in TABLES:
        fields = list_bitable_fields(tok, APP_TOKEN, table_id)
        records = fetch_all_bitable_records(tok, APP_TOKEN, table_id)
        parsed = parse_table(table_name, fields, records)
        table_stats[table_name] = {
            "raw": len(records),
            "parsed": len(parsed),
            "by_source": dict(Counter(p.status_source for p in parsed)),
            "by_status": dict(Counter(p.status for p in parsed)),
        }
        all_records.extend(parsed)

    HIGH_CONF = {"supervisor_opinion", "confirmed", "score_inferred"}
    holdout = [r for r in all_records if r.status_source in HIGH_CONF and r.docx_token]
    print(f"\nholdout（高置信 + 有 docx）: {len(holdout)} 条")
    print("by table:", dict(Counter(r.table_source for r in holdout)))
    print("by status:", dict(Counter(r.status for r in holdout)))

    tokens = [r.docx_token for r in holdout]
    success, failed = fetch_many(tokens, force=False)
    print(f"docx fetch: ok={len(success)} failed={len(failed)}")

    ready = []
    for r in holdout:
        c = success.get(r.docx_token)
        if not c:
            continue
        r.text_content = c
        ready.append(r)
    print(f"准备打分: {len(ready)} 条")

    sem = asyncio.Semaphore(8)

    async def _bounded(rec):
        async with sem:
            return rec, await _predict_tolerant(rec, handbook_text)

    print("\n开始评分（并发 8）...")
    results = await asyncio.gather(*[_bounded(r) for r in ready])

    rows = []
    for actual, pred in results:
        if pred is None:
            rows.append({
                "title": actual.title,
                "table": actual.table_source,
                "actual_status": actual.status,
                "actual_mean_score": actual.mean_score,
                "actual_range": list(actual.score_range) if actual.score_range else None,
                "predicted_score": None,
                "predicted_status": None,
                "fail": True,
            })
            continue
        rows.append({
            "title": actual.title,
            "table": actual.table_source,
            "actual_status": actual.status,
            "actual_mean_score": actual.mean_score,
            "actual_range": list(actual.score_range) if actual.score_range else None,
            "predicted_score": pred.predicted_score,
            "predicted_status": pred.predicted_status,
            "fail": False,
        })

    valid = [r for r in rows if not r["fail"]]
    n = len(valid)
    print(f"\n=== 评分完成: {n}/{len(rows)} 成功 ===")

    # 1. 全样本预测分排序展示
    print("\n=== 全部预测分（降序）===")
    print(f"{'title':<40}{'table':<6}{'actual_status':<14}{'pred_score':>10}{'pred_status':>12}")
    for r in sorted(valid, key=lambda x: -x["predicted_score"]):
        print(f"{r['title'][:38]:<40}{r['table']:<6}{r['actual_status']:<14}"
              f"{r['predicted_score']:>10}{r['predicted_status']:>12}")

    # 2. 按 actual_status 分组的分数分布
    by_status_scores = defaultdict(list)
    for r in valid:
        by_status_scores[r["actual_status"]].append(r["predicted_score"])

    print("\n=== 预测分按 actual_status 分组（discrimination 体检）===")
    print(f"{'status':<6}{'n':>4}{'mean':>8}{'median':>8}{'min':>6}{'max':>6}{'std':>8}")
    status_dist_summary = {}
    for s in ["签", "改", "拒"]:
        scores = by_status_scores.get(s, [])
        if not scores:
            continue
        m = statistics.mean(scores)
        med = statistics.median(scores)
        sd = statistics.stdev(scores) if len(scores) > 1 else 0.0
        status_dist_summary[s] = {"n": len(scores), "mean": m, "median": med,
                                   "min": min(scores), "max": max(scores), "std": sd}
        print(f"{s:<6}{len(scores):>4}{m:>8.1f}{med:>8.1f}{min(scores):>6}{max(scores):>6}{sd:>8.1f}")

    # 3. MAE on samples with ground-truth mean_score
    with_truth = [r for r in valid if r["actual_mean_score"] is not None]
    if with_truth:
        errors = [abs(r["predicted_score"] - r["actual_mean_score"]) for r in with_truth]
        in_range = sum(
            1 for r in with_truth
            if r["actual_range"] and r["actual_range"][0] <= r["predicted_score"] <= r["actual_range"][1]
        )
        mae = sum(errors) / len(errors)
        print(f"\n=== 真实均分对照 (n={len(with_truth)}) ===")
        print(f"MAE: {mae:.1f}")
        print(f"区间命中率: {in_range / len(with_truth):.0%}  ({in_range}/{len(with_truth)})")
        for r in with_truth:
            print(f"  {r['title'][:30]:<32} actual_mean={r['actual_mean_score']} "
                  f"range={r['actual_range']} pred={r['predicted_score']} "
                  f"err={abs(r['predicted_score'] - r['actual_mean_score']):.1f}")
    else:
        mae = None
        in_range = 0

    # 写报告
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = OUT_DIR / f"holdout_0508_v{version}_score_{ts}.json"
    md_path = OUT_DIR / f"holdout_0508_v{version}_score_{ts}.md"

    json_path.write_text(json.dumps({
        "handbook_version": version,
        "app_token": APP_TOKEN,
        "tables": table_stats,
        "n_holdout": n,
        "n_failed_predict": len(rows) - n,
        "score_dist_by_actual_status": status_dist_summary,
        "mae_with_truth": mae,
        "n_with_truth": len(with_truth),
        "rows": rows,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# Holdout 评分报告 — handbook v{version}",
        f"> 数据源：飞书 bitable {APP_TOKEN}（外部待审核剧本0508）",
        f"> 生成时间：{ts}",
        f"> 主输出：预测分（0-100），签/改/拒 仅作参考。",
        "",
        f"## 总览",
        f"- 样本数：**{n}**（LLM 失败 {len(rows) - n}）",
        f"- 含真实均分的样本：{len(with_truth)}",
    ]
    if mae is not None:
        lines.append(f"- MAE（vs 真实均分）：**{mae:.1f}**")
        lines.append(f"- 区间命中率：{in_range / len(with_truth):.0%} ({in_range}/{len(with_truth)})")
    lines += ["", "## 按 actual_status 分组的预测分分布",
              "", "| status | n | mean | median | min | max | std |",
              "|---|---|---|---|---|---|---|"]
    for s in ["签", "改", "拒"]:
        d = status_dist_summary.get(s)
        if not d:
            continue
        lines.append(f"| {s} | {d['n']} | {d['mean']:.1f} | {d['median']:.1f} | "
                     f"{d['min']} | {d['max']} | {d['std']:.1f} |")

    lines += ["", "## 全部预测分（按预测分降序）", "",
              "| 剧本 | 表 | actual_status | pred_score | pred_status | actual_mean | range |",
              "|---|---|---|---|---|---|---|"]
    for r in sorted(valid, key=lambda x: -x["predicted_score"]):
        am = r["actual_mean_score"] if r["actual_mean_score"] is not None else "-"
        ar = f"{r['actual_range']}" if r["actual_range"] else "-"
        lines.append(f"| {r['title'][:30]} | {r['table']} | {r['actual_status']} | "
                     f"**{r['predicted_score']}** | {r['predicted_status']} | {am} | {ar} |")

    if rows and any(r["fail"] for r in rows):
        lines += ["", "## LLM 评分失败"]
        for r in rows:
            if r["fail"]:
                lines.append(f"- {r['title']} ({r['table']})")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告：{md_path}")
    print(f"原始：{json_path}")


if __name__ == "__main__":
    asyncio.run(main())
