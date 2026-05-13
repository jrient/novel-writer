"""
合并 holdout + n_samples=3 + 线性校准
============================================

在 merged_score_holdout 基础上：
- D：每条样本预测 3 次取均值（temp=0 仍有 ±5 抖动，平均能压噪声底线）
- B：在真分子集上拟合 actual = a * pred + b，把模型输出的 [70,79] 拉伸到 [70,85]
     校准后重算 MAE / Spearman / 区间命中率

Calibration 拟合策略：
- 主结果：拟合于全部 22 条真分（in-sample）→ 看天花板效应是否消除
- 诚实结果：leave-one-out CV，每个样本用其余 21 条拟合后预测自己

Calibration 系数最终落到 outputs/handbook/calibration_v{version}.json，
供线上评分服务（rubric_score_service）按需启用。
"""

from __future__ import annotations

import asyncio
import json
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from script_rubric.config import HANDBOOK_DIR
from script_rubric.feishu.feishu_common import (
    get_tenant_access_token,
    list_bitable_fields,
    fetch_all_bitable_records,
)
from script_rubric.pipeline.parse_bitable import parse_table, parse_bitable_json
from script_rubric.pipeline.fetch_docx import fetch_many
from script_rubric.pipeline.backtest import predict_one

APP_TOKEN_0508 = "IXbHb8BiuaCjutsu2eJcDBL6nCf"
TABLES_0508 = [("tblLaAiHPjepItfL", "冲量"), ("tblYb5CVaK9C66O4", "精品")]
TRAIN_POOL_JSON = Path("/app/script_rubric/data/bitable_rubric.json")
OUT_DIR = Path("/app/script_rubric/outputs/experiments")
N_SAMPLES = 3


def _latest_handbook_version() -> int:
    versions = []
    for p in HANDBOOK_DIR.glob("handbook_v*.md"):
        try:
            versions.append(int(p.stem.split("v")[-1]))
        except ValueError:
            continue
    return max(versions) if versions else 1


def _spearman(xs, ys):
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
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                ranks[idx[k]] = avg
            i = j + 1
        return ranks

    rx, ry = rank(xs), rank(ys)
    mx, my = statistics.mean(rx), statistics.mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return num / (dx * dy) if dx and dy else 0.0


def _linfit(xs: list[float], ys: list[float]) -> tuple[float, float]:
    """OLS 一元线性回归 y = a*x + b 返回 (a, b)。"""
    n = len(xs)
    if n < 2:
        return 1.0, 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    a = num / den if den else 1.0
    b = my - a * mx
    return a, b


def _metrics(rows, score_field: str) -> dict:
    truth = [r for r in rows if r["actual_mean_score"] is not None and r[score_field] is not None]
    if not truth:
        return {"n": 0}
    a = [r["actual_mean_score"] for r in truth]
    p = [r[score_field] for r in truth]
    rho = _spearman(a, p)
    mae = statistics.mean(abs(x - y) for x, y in zip(a, p))
    in_range = sum(
        1 for r in truth
        if r["actual_range"] and r["actual_range"][0] <= r[score_field] <= r["actual_range"][1]
    )
    return {
        "n": len(truth),
        "spearman": rho,
        "mae": mae,
        "in_range": in_range,
        "in_range_rate": in_range / len(truth),
    }


async def main():
    version = _latest_handbook_version()
    handbook_text = (HANDBOOK_DIR / f"handbook_v{version}.md").read_text(encoding="utf-8")
    print(f"使用 handbook_v{version}, n_samples={N_SAMPLES}")

    # 拉数据
    train_recs = parse_bitable_json(TRAIN_POOL_JSON)
    train_truth = [r for r in train_recs if r.mean_score is not None and r.docx_token]
    for r in train_truth:
        r.text_file = "train_pool"

    tok = get_tenant_access_token()
    new_recs = []
    for tid, tname in TABLES_0508:
        fields = list_bitable_fields(tok, APP_TOKEN_0508, tid)
        records = fetch_all_bitable_records(tok, APP_TOKEN_0508, tid)
        new_recs.extend(parse_table(tname, fields, records))

    HIGH = {"supervisor_opinion", "confirmed", "score_inferred"}
    new_holdout = [r for r in new_recs if r.status_source in HIGH and r.docx_token]
    for r in new_holdout:
        r.text_file = "holdout_0508"

    all_set = train_truth + new_holdout
    tokens = list({r.docx_token for r in all_set if r.docx_token})
    success, _ = fetch_many(tokens, force=False)
    ready = []
    for r in all_set:
        c = success.get(r.docx_token) if r.docx_token else None
        if not c:
            continue
        r.text_content = c
        ready.append(r)
    print(f"ready: {len(ready)} (train_pool {sum(1 for r in ready if r.text_file=='train_pool')}, "
          f"holdout_0508 {sum(1 for r in ready if r.text_file=='holdout_0508')})")

    # 评分（n_samples=3 取均）—— predict_one 内部串行 N 次
    sem = asyncio.Semaphore(6)

    async def _bounded(rec):
        async with sem:
            return rec, await predict_one(rec, handbook_text, n_samples=N_SAMPLES)

    print(f"\n评分中...（每条 LLM 调用 {N_SAMPLES} 次，约 {len(ready) * N_SAMPLES} 次总调用）")
    results = await asyncio.gather(*[_bounded(r) for r in ready])

    rows = []
    for actual, pred in results:
        rows.append({
            "title": actual.title,
            "source": actual.text_file,
            "table": actual.table_source,
            "actual_status": actual.status,
            "actual_mean_score": actual.mean_score,
            "actual_range": list(actual.score_range) if actual.score_range else None,
            "predicted_score": pred.predicted_score if pred else None,
            "predicted_status": pred.predicted_status if pred else None,
            "fail": pred is None,
        })

    valid = [r for r in rows if not r["fail"]]
    print(f"成功 {len(valid)}/{len(rows)}")

    # === Raw 指标 ===
    raw_metrics = _metrics(valid, "predicted_score")

    # === 线性校准（in-sample, on truth subset）===
    truth = [r for r in valid if r["actual_mean_score"] is not None]
    pred_arr = [r["predicted_score"] for r in truth]
    actual_arr = [r["actual_mean_score"] for r in truth]
    a, b = _linfit(pred_arr, actual_arr)
    print(f"\n=== 线性校准拟合（n={len(truth)}）===")
    print(f"  actual = {a:.3f} * pred + {b:.2f}")

    for r in valid:
        r["calibrated_score"] = round(a * r["predicted_score"] + b) if r["predicted_score"] is not None else None

    cal_metrics = _metrics(valid, "calibrated_score")

    # === LOO CV：诚实校准 MAE ===
    loo_errors = []
    loo_in_range = 0
    for i, target in enumerate(truth):
        rest_p = [truth[j]["predicted_score"] for j in range(len(truth)) if j != i]
        rest_a = [truth[j]["actual_mean_score"] for j in range(len(truth)) if j != i]
        a_loo, b_loo = _linfit(rest_p, rest_a)
        cal = a_loo * target["predicted_score"] + b_loo
        loo_errors.append(abs(cal - target["actual_mean_score"]))
        if target["actual_range"] and target["actual_range"][0] <= round(cal) <= target["actual_range"][1]:
            loo_in_range += 1

    loo_mae = statistics.mean(loo_errors) if loo_errors else None
    loo_rate = loo_in_range / len(truth) if truth else None

    # === 输出对比 ===
    print("\n=== 指标对比 ===")
    print(f"{'方案':<28}{'n':>4}{'ρ':>10}{'MAE':>10}{'in_range':>12}")
    print(f"{'raw (n_samples=3)':<28}{raw_metrics['n']:>4}"
          f"{raw_metrics['spearman']:>10.3f}{raw_metrics['mae']:>10.2f}"
          f"{raw_metrics['in_range_rate']:>12.0%}")
    print(f"{'+ linear cal (in-sample)':<28}{cal_metrics['n']:>4}"
          f"{cal_metrics['spearman']:>10.3f}{cal_metrics['mae']:>10.2f}"
          f"{cal_metrics['in_range_rate']:>12.0%}")
    print(f"{'+ linear cal (LOO)':<28}{len(truth):>4}"
          f"{'-':>10}{loo_mae:>10.2f}{loo_rate:>12.0%}")

    # === 全样本预测分按 status ===
    print("\n=== 校准后预测分按 actual_status 分组 ===")
    by_status = defaultdict(list)
    for r in valid:
        by_status[r["actual_status"]].append(r["calibrated_score"])
    print(f"{'status':<6}{'n':>4}{'mean':>8}{'median':>8}{'min':>6}{'max':>6}{'std':>8}")
    cal_status_dist = {}
    for s in ["签", "改", "拒"]:
        sc = by_status.get(s, [])
        if not sc:
            continue
        m = statistics.mean(sc)
        med = statistics.median(sc)
        sd = statistics.stdev(sc) if len(sc) > 1 else 0.0
        cal_status_dist[s] = {"n": len(sc), "mean": m, "median": med,
                               "min": min(sc), "max": max(sc), "std": sd}
        print(f"{s:<6}{len(sc):>4}{m:>8.1f}{med:>8.1f}{min(sc):>6}{max(sc):>6}{sd:>8.1f}")

    # === 真分逐条对照 ===
    print("\n=== 真分逐条（按 actual 排序） — pred / cal ===")
    print(f"{'title':<35}{'src':<14}{'actual':>8}{'pred':>6}{'cal':>6}{'err_raw':>10}{'err_cal':>10}")
    for r in sorted(truth, key=lambda x: x["actual_mean_score"]):
        er = r["predicted_score"] - r["actual_mean_score"]
        ec = r["calibrated_score"] - r["actual_mean_score"]
        print(f"{r['title'][:33]:<35}{r['source']:<14}"
              f"{r['actual_mean_score']:>8}{r['predicted_score']:>6}"
              f"{r['calibrated_score']:>6}{er:>+10.1f}{ec:>+10.1f}")

    # === 写出 ===
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = OUT_DIR / f"calibrated_v{version}_{ts}.json"
    md_path = OUT_DIR / f"calibrated_v{version}_{ts}.md"

    # 校准系数：保存到 handbook 目录，供线上服务用
    calib_path = HANDBOOK_DIR / f"calibration_v{version}.json"
    calib_path.write_text(json.dumps({
        "handbook_version": version,
        "n_samples_recommended": N_SAMPLES,
        "linear": {"a": a, "b": b},
        "fit_n": len(truth),
        "raw_metrics": raw_metrics,
        "calibrated_metrics": cal_metrics,
        "loo_mae": loo_mae,
        "fit_at": datetime.now().isoformat(),
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n校准系数: {calib_path}")

    json_path.write_text(json.dumps({
        "handbook_version": version,
        "n_samples": N_SAMPLES,
        "linear": {"a": a, "b": b},
        "raw_metrics": raw_metrics,
        "cal_metrics": cal_metrics,
        "loo_mae": loo_mae,
        "loo_in_range_rate": loo_rate,
        "cal_status_dist": cal_status_dist,
        "rows": rows,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# 校准 holdout 报告 — handbook v{version}",
        f"> 生成: {ts} | n_samples={N_SAMPLES} | 数据={len(valid)}（含真分 {len(truth)}）",
        "",
        "## 指标对比",
        "",
        "| 方案 | n | Spearman ρ | MAE | 区间命中率 |",
        "|---|---|---|---|---|",
        f"| raw (n_samples={N_SAMPLES}) | {raw_metrics['n']} | "
        f"{raw_metrics['spearman']:.3f} | {raw_metrics['mae']:.2f} | "
        f"{raw_metrics['in_range_rate']:.0%} |",
        f"| + 线性校准（in-sample）| {cal_metrics['n']} | "
        f"{cal_metrics['spearman']:.3f} | {cal_metrics['mae']:.2f} | "
        f"{cal_metrics['in_range_rate']:.0%} |",
        f"| + 线性校准（LOO 诚实）| {len(truth)} | - | "
        f"{loo_mae:.2f} | {loo_rate:.0%} |",
        "",
        "## 校准公式",
        f"- `actual = {a:.3f} * pred + {b:.2f}`",
        f"- 拟合于 {len(truth)} 条真分样本",
        f"- 已存：`{calib_path}`",
        "",
        "## 真分逐条（按 actual 排序）",
        "",
        "| 剧本 | 来源 | actual | range | raw | cal | err_raw | err_cal |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in sorted(truth, key=lambda x: x["actual_mean_score"]):
        er = r["predicted_score"] - r["actual_mean_score"]
        ec = r["calibrated_score"] - r["actual_mean_score"]
        ar = f"{r['actual_range']}" if r["actual_range"] else "-"
        lines.append(f"| {r['title'][:30]} | {r['source']} | {r['actual_mean_score']} | {ar} | "
                     f"{r['predicted_score']} | {r['calibrated_score']} | {er:+.1f} | {ec:+.1f} |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {md_path}")
    print(f"原始: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
