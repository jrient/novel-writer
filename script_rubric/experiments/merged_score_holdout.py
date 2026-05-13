"""
合并真分 holdout：bitable_rubric.json (18 条训练池真分) + 0508 (21 条新数据)
=================================================================================

主输出 = predicted_score。
指标：
- 全样本 Spearman（pred vs actual_mean_score） + MAE
- 按 actual_status 分组的 pred 分布（含训练 + 新数据混合）
- 标注每条样本是 train_pool 还是 0508_holdout

注意：训练池 18 条是 v14 的 in-sample 数据，不算严格 holdout，仅用于
扩大真分样本量看校准/排序一致性。
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
from script_rubric.pipeline.parse_bitable import parse_table, parse_bitable_json
from script_rubric.pipeline.fetch_docx import fetch_many
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json
from script_rubric.models import PredictResult

APP_TOKEN_0508 = "IXbHb8BiuaCjutsu2eJcDBL6nCf"
TABLES_0508 = [("tblLaAiHPjepItfL", "冲量"), ("tblYb5CVaK9C66O4", "精品")]
TRAIN_POOL_JSON = Path("/app/script_rubric/data/bitable_rubric.json")
OUT_DIR = Path("/app/script_rubric/outputs/experiments")


def _latest_handbook_version() -> int:
    versions = []
    for p in HANDBOOK_DIR.glob("handbook_v*.md"):
        try:
            versions.append(int(p.stem.split("v")[-1]))
        except ValueError:
            continue
    return max(versions) if versions else 1


async def predict_tolerant(record, handbook_text: str) -> PredictResult | None:
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
        ds = data.get("dimension_scores")
        if isinstance(ds, dict):
            data["dimension_scores"] = {k: round(v) if isinstance(v, float) else v for k, v in ds.items()}
        return PredictResult.model_validate(data)
    except Exception as e:
        print(f"  [FAIL] {record.title[:30]}: {e}")
        return None


def _spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None

    def rank(arr):
        idx = sorted(range(len(arr)), key=lambda i: arr[i])
        ranks = [0.0] * len(arr)
        i = 0
        while i < len(arr):
            j = i
            while j + 1 < len(arr) and arr[idx[j + 1]] == arr[idx[i]]:
                j += 1
            avg_rank = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[idx[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx) ** 0.5
    den_y = sum((b - my) ** 2 for b in ry) ** 0.5
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


async def main():
    version = _latest_handbook_version()
    handbook_text = (HANDBOOK_DIR / f"handbook_v{version}.md").read_text(encoding="utf-8")
    print(f"使用 handbook_v{version}")

    # === 1. 训练池真分样本 ===
    train_recs = parse_bitable_json(TRAIN_POOL_JSON)
    train_truth = [r for r in train_recs if r.mean_score is not None and r.docx_token]
    print(f"\n训练池真分样本（in-sample）: {len(train_truth)}")
    for r in train_truth:
        r.text_file = "train_pool"  # 标记来源

    # === 2. 0508 holdout ===
    tok = get_tenant_access_token()
    new_recs = []
    for table_id, table_name in TABLES_0508:
        fields = list_bitable_fields(tok, APP_TOKEN_0508, table_id)
        records = fetch_all_bitable_records(tok, APP_TOKEN_0508, table_id)
        parsed = parse_table(table_name, fields, records)
        new_recs.extend(parsed)

    HIGH_CONF = {"supervisor_opinion", "confirmed", "score_inferred"}
    new_holdout = [r for r in new_recs if r.status_source in HIGH_CONF and r.docx_token]
    for r in new_holdout:
        r.text_file = "holdout_0508"
    print(f"0508 holdout 样本（out-of-sample）: {len(new_holdout)}")

    # === 3. 合并 + 拉正文 ===
    all_set = train_truth + new_holdout
    tokens = list({r.docx_token for r in all_set if r.docx_token})
    success, failed = fetch_many(tokens, force=False)
    print(f"\ndocx fetch: ok={len(success)} fail={len(failed)}")

    ready = []
    for r in all_set:
        c = success.get(r.docx_token) if r.docx_token else None
        if not c:
            continue
        r.text_content = c
        ready.append(r)
    print(f"ready: {len(ready)}")

    # === 4. 并发评分 ===
    sem = asyncio.Semaphore(8)

    async def _bounded(rec):
        async with sem:
            return rec, await predict_tolerant(rec, handbook_text)

    print("\n评分（并发 8）...")
    results = await asyncio.gather(*[_bounded(r) for r in ready])

    rows = []
    for actual, pred in results:
        rows.append({
            "title": actual.title,
            "source": actual.text_file,  # train_pool / holdout_0508
            "table": actual.table_source,
            "actual_status": actual.status,
            "actual_mean_score": actual.mean_score,
            "actual_range": list(actual.score_range) if actual.score_range else None,
            "predicted_score": pred.predicted_score if pred else None,
            "predicted_status": pred.predicted_status if pred else None,
            "fail": pred is None,
        })

    valid = [r for r in rows if not r["fail"]]
    n = len(valid)
    print(f"\n=== 完成 {n}/{len(rows)} ===")

    # === 5. Spearman + MAE on truth subset ===
    truth_rows = [r for r in valid if r["actual_mean_score"] is not None]
    actual_arr = [r["actual_mean_score"] for r in truth_rows]
    pred_arr = [r["predicted_score"] for r in truth_rows]
    rho = _spearman(actual_arr, pred_arr)
    mae = statistics.mean(abs(a - p) for a, p in zip(actual_arr, pred_arr)) if truth_rows else None
    in_range = sum(
        1 for r in truth_rows
        if r["actual_range"] and r["actual_range"][0] <= r["predicted_score"] <= r["actual_range"][1]
    )

    print("\n=== 真分对照（合并 in-sample + 0508 holdout）===")
    print(f"n_truth: {len(truth_rows)}")
    print(f"Spearman ρ (pred vs actual_mean): {rho:.3f}" if rho is not None else "Spearman: N/A")
    print(f"MAE: {mae:.2f}" if mae is not None else "MAE: N/A")
    print(f"区间命中率: {in_range/len(truth_rows):.0%} ({in_range}/{len(truth_rows)})" if truth_rows else "")

    # 分来源
    for src in ["train_pool", "holdout_0508"]:
        sub = [r for r in truth_rows if r["source"] == src]
        if not sub:
            continue
        a = [r["actual_mean_score"] for r in sub]
        p = [r["predicted_score"] for r in sub]
        rs = _spearman(a, p)
        ms = statistics.mean(abs(x - y) for x, y in zip(a, p))
        rs_s = f"{rs:.3f}" if rs is not None else "NA"
        print(f"  {src}: n={len(sub)} ρ={rs_s} MAE={ms:.2f}")

    # === 6. 按 actual_status 分组的 pred 分布（全样本）===
    by_status = defaultdict(list)
    for r in valid:
        by_status[r["actual_status"]].append(r["predicted_score"])

    print("\n=== 预测分按 actual_status 分组（n=39）===")
    print(f"{'status':<6}{'n':>4}{'mean':>8}{'median':>8}{'min':>6}{'max':>6}{'std':>8}")
    status_dist = {}
    for s in ["签", "改", "拒"]:
        if s not in by_status:
            continue
        sc = by_status[s]
        m = statistics.mean(sc)
        med = statistics.median(sc)
        sd = statistics.stdev(sc) if len(sc) > 1 else 0.0
        status_dist[s] = {"n": len(sc), "mean": m, "median": med,
                          "min": min(sc), "max": max(sc), "std": sd}
        print(f"{s:<6}{len(sc):>4}{m:>8.1f}{med:>8.1f}{min(sc):>6}{max(sc):>6}{sd:>8.1f}")

    # === 7. 真分 scatter 表（actual sorted）===
    print("\n=== 真分对照逐条（按 actual 排序）===")
    print(f"{'title':<35}{'src':<14}{'actual':>8}{'pred':>8}{'err':>8}{'in_rng':>8}")
    for r in sorted(truth_rows, key=lambda x: x["actual_mean_score"]):
        err = r["predicted_score"] - r["actual_mean_score"]
        ir = "Y" if r["actual_range"] and r["actual_range"][0] <= r["predicted_score"] <= r["actual_range"][1] else "N"
        print(f"{r['title'][:33]:<35}{r['source']:<14}{r['actual_mean_score']:>8}"
              f"{r['predicted_score']:>8}{err:>+8.1f}{ir:>8}")

    # === 8. 写报告 ===
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = OUT_DIR / f"merged_score_v{version}_{ts}.json"
    md_path = OUT_DIR / f"merged_score_v{version}_{ts}.md"

    json_path.write_text(json.dumps({
        "handbook_version": version,
        "n_total": n,
        "n_truth": len(truth_rows),
        "spearman": rho,
        "mae": mae,
        "in_range_rate": in_range / len(truth_rows) if truth_rows else None,
        "status_dist": status_dist,
        "rows": rows,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# 合并 holdout 评分报告 — handbook v{version}",
        f"> 数据：训练池真分样本 ({len(train_truth)}) + 0508 holdout ({len(new_holdout)})",
        f"> 生成时间：{ts}",
        "",
        "## 指标（仅真分子集）",
        f"- n_truth: **{len(truth_rows)}**",
        f"- **Spearman ρ**: {rho:.3f}" if rho is not None else "- Spearman: N/A",
        f"- **MAE**: {mae:.2f}" if mae is not None else "",
        f"- 区间命中率: {in_range}/{len(truth_rows)}",
        "",
        "## 预测分按 actual_status 分组（全样本 n={})".format(n),
        "",
        "| status | n | mean | median | min | max | std |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in ["签", "改", "拒"]:
        d = status_dist.get(s)
        if not d:
            continue
        lines.append(f"| {s} | {d['n']} | {d['mean']:.1f} | {d['median']:.1f} | "
                     f"{d['min']} | {d['max']} | {d['std']:.1f} |")

    lines += ["", "## 真分对照（按 actual 排序）", "",
              "| 剧本 | 来源 | actual_mean | range | predicted | err | in_range |",
              "|---|---|---|---|---|---|---|"]
    for r in sorted(truth_rows, key=lambda x: x["actual_mean_score"]):
        err = r["predicted_score"] - r["actual_mean_score"]
        ar = f"{r['actual_range']}" if r["actual_range"] else "-"
        ir = "Y" if r["actual_range"] and r["actual_range"][0] <= r["predicted_score"] <= r["actual_range"][1] else "N"
        lines.append(f"| {r['title'][:30]} | {r['source']} | {r['actual_mean_score']} | {ar} | "
                     f"{r['predicted_score']} | {err:+.1f} | {ir} |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告：{md_path}")
    print(f"原始：{json_path}")


if __name__ == "__main__":
    asyncio.run(main())
