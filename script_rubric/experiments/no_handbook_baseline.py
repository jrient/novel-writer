"""
No-Handbook Baseline 实验
==========================

诊断 handbook v14 是否真的提供信息：让 LLM 在不看 handbook 的情况下评分，
对比 with-handbook 的指标。

如果 no-handbook 持平或更好 → handbook 在制造噪声，整个体系需重做。
如果 with-handbook 显著更好 → 体系有效，问题在于校准/训练池窄带。

数据：merged_score 用过的 22 条真分样本（train_pool 18 + holdout_0508 4）
方法：n_samples=3 取均，prompt 仅给 0-100 评分任务+三档阈值，无任何手册内容
"""

from __future__ import annotations

import asyncio
import json
import statistics
from collections import defaultdict
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
from script_rubric.pipeline.llm_client import get_client, call_llm, extract_json
from script_rubric.models import PredictResult

APP_TOKEN_0508 = "IXbHb8BiuaCjutsu2eJcDBL6nCf"
TABLES_0508 = [("tblLaAiHPjepItfL", "冲量"), ("tblYb5CVaK9C66O4", "精品")]
TRAIN_POOL_JSON = Path("/app/script_rubric/data/bitable_rubric.json")
OUT_DIR = Path("/app/script_rubric/outputs/experiments")
N_SAMPLES = 3

NO_HANDBOOK_SYSTEM = "你是一位资深剧本评审员。严格按 JSON 格式输出。"

NO_HANDBOOK_USER_TEMPLATE = """请对下面这个短剧/网文剧本片段做整体质量评估，给出 0-100 分。

评分参照：
- 80 及以上 = 签（高质量、可直接采用）
- 70-79 = 改（有亮点但需修改）
- 70 以下 = 拒（不达标）

仅输出 JSON，结构如下（不要 markdown 围栏，不要任何额外文本）：
{{
  "title": "{title}",
  "predicted_score": <0-100 的整数>,
  "predicted_status": "签" 或 "改" 或 "拒",
  "comments": ["简短评价 1", "简短评价 2", ...]
}}

剧本类型: {source_type}
剧本题材: {genre}
标题: {title}
正文:
---
{text_content}
---"""


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


async def predict_no_handbook(record, n_samples: int = N_SAMPLES) -> PredictResult | None:
    text = (record.text_content or "").strip()
    if len(text) < 100:
        return None

    user_prompt = NO_HANDBOOK_USER_TEMPLATE.format(
        title=record.title,
        source_type=record.source_type or "短剧",
        genre=record.genre or "未标注",
        text_content=text[:30000],
    )
    client = get_client()
    samples = []
    for _ in range(n_samples):
        try:
            raw = await call_llm(client, NO_HANDBOOK_SYSTEM, user_prompt, max_retries=2, temperature=0.0)
            data = extract_json(raw)
            if isinstance(data.get("predicted_score"), float):
                data["predicted_score"] = round(data["predicted_score"])
            data.setdefault("dimension_scores", {})
            data.setdefault("red_flags_hit", [])
            data.setdefault("green_flags_hit", [])
            samples.append(PredictResult.model_validate(data))
        except Exception as e:
            print(f"  [FAIL] {record.title[:30]}: {e}")
            continue
    if not samples:
        return None
    if len(samples) == 1:
        return samples[0]

    avg = round(sum(s.predicted_score for s in samples) / len(samples))
    status = "签" if avg >= 80 else ("改" if avg >= 70 else "拒")
    base = samples[0]
    return PredictResult(
        title=base.title,
        predicted_score=avg,
        predicted_status=status,
        dimension_scores=base.dimension_scores,
        comments=base.comments,
        red_flags_hit=[],
        green_flags_hit=[],
    )


async def main():
    version = _latest_handbook_version()
    print(f"参照 handbook_v{version}（仅作对比，本实验不喂入）, n_samples={N_SAMPLES}")

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
    print(f"ready: {len(ready)}")

    sem = asyncio.Semaphore(6)

    async def _bounded(rec):
        async with sem:
            return rec, await predict_no_handbook(rec, n_samples=N_SAMPLES)

    print(f"\n评分（NO HANDBOOK，n_samples={N_SAMPLES}）...")
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

    truth = [r for r in valid if r["actual_mean_score"] is not None]
    a = [r["actual_mean_score"] for r in truth]
    p = [r["predicted_score"] for r in truth]
    rho = _spearman(a, p) if truth else None
    mae = statistics.mean(abs(x - y) for x, y in zip(a, p)) if truth else None
    in_range = sum(
        1 for r in truth
        if r["actual_range"] and r["actual_range"][0] <= r["predicted_score"] <= r["actual_range"][1]
    )

    by_status = defaultdict(list)
    for r in valid:
        by_status[r["actual_status"]].append(r["predicted_score"])

    # status accuracy
    status_hits = sum(1 for r in valid if r["predicted_status"] == r["actual_status"])

    print("\n=== 结果 (NO HANDBOOK baseline) ===")
    print(f"完成: {len(valid)}/{len(rows)}")
    print(f"n_truth: {len(truth)}")
    print(f"Spearman ρ: {rho:.3f}" if rho is not None else "ρ: NA")
    print(f"MAE: {mae:.2f}")
    print(f"区间命中率: {in_range}/{len(truth)} = {in_range/len(truth):.0%}")
    print(f"status accuracy: {status_hits}/{len(valid)} = {status_hits/len(valid):.0%}")

    print("\n=== 预测分按 actual_status 分组 ===")
    print(f"{'status':<6}{'n':>4}{'mean':>8}{'median':>8}{'min':>6}{'max':>6}{'std':>8}")
    status_dist = {}
    for s in ["签", "改", "拒"]:
        sc = by_status.get(s, [])
        if not sc:
            continue
        m = statistics.mean(sc)
        med = statistics.median(sc)
        sd = statistics.stdev(sc) if len(sc) > 1 else 0.0
        status_dist[s] = {"n": len(sc), "mean": m, "median": med,
                          "min": min(sc), "max": max(sc), "std": sd}
        print(f"{s:<6}{len(sc):>4}{m:>8.1f}{med:>8.1f}{min(sc):>6}{max(sc):>6}{sd:>8.1f}")

    print("\n=== 真分逐条 ===")
    print(f"{'title':<35}{'src':<14}{'actual':>8}{'pred':>6}{'err':>8}")
    for r in sorted(truth, key=lambda x: x["actual_mean_score"]):
        err = r["predicted_score"] - r["actual_mean_score"]
        print(f"{r['title'][:33]:<35}{r['source']:<14}"
              f"{r['actual_mean_score']:>8}{r['predicted_score']:>6}{err:>+8.1f}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = OUT_DIR / f"no_handbook_baseline_{ts}.json"
    md_path = OUT_DIR / f"no_handbook_baseline_{ts}.md"

    json_path.write_text(json.dumps({
        "experiment": "no_handbook_baseline",
        "n_samples": N_SAMPLES,
        "n_total": len(valid),
        "n_truth": len(truth),
        "spearman": rho,
        "mae": mae,
        "in_range": in_range,
        "in_range_rate": in_range / len(truth) if truth else None,
        "status_accuracy": status_hits / len(valid) if valid else None,
        "status_dist": status_dist,
        "rows": rows,
    }, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# No-Handbook Baseline — {ts}",
        f"> n={len(valid)}, n_truth={len(truth)}, n_samples={N_SAMPLES}",
        "",
        "## 指标",
        f"- Spearman ρ: **{rho:.3f}**" if rho is not None else "- ρ: NA",
        f"- MAE: **{mae:.2f}**",
        f"- 区间命中率: {in_range}/{len(truth)} = {in_range/len(truth):.0%}",
        f"- status accuracy: {status_hits}/{len(valid)} = {status_hits/len(valid):.0%}",
        "",
        "## 预测分按 actual_status 分组",
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

    lines += ["", "## 真分逐条", "",
              "| 剧本 | 来源 | actual | range | pred | err |",
              "|---|---|---|---|---|---|"]
    for r in sorted(truth, key=lambda x: x["actual_mean_score"]):
        err = r["predicted_score"] - r["actual_mean_score"]
        ar = f"{r['actual_range']}" if r["actual_range"] else "-"
        lines.append(f"| {r['title'][:30]} | {r['source']} | {r['actual_mean_score']} | {ar} | "
                     f"{r['predicted_score']} | {err:+.1f} |")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告: {md_path}")
    print(f"原始: {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
