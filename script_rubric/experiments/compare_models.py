"""
模型对比实验：gemini-3.1-pro-preview vs deepseek-v4-pro
========================================================

在 status_source=supervisor_opinion 的冲量记录上跑两遍 backtest_predict，
对比：
- status accuracy（vs 主管意见真值）
- 严重误判率（签↔拒 跨级）
- 模型间一致率
- 平均预测分 / 维度均分

零侵入：不改 backtest.py / llm_client.py，自己构造 client + prompt。

用法:
  python -m script_rubric.experiments.compare_models [--n 10] [--no-leak]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI

load_dotenv()

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from script_rubric.config import BITABLE_RUBRIC_JSON, DRAMA_DIR, HANDBOOK_DIR, PROMPT_DIR
from script_rubric.pipeline.parse_bitable import parse_bitable_json
from script_rubric.pipeline.match_texts import match_texts
from script_rubric.pipeline.llm_client import extract_json

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("compare_models")


# ───────── 模型配置 ─────────
MODELS = {
    "gemini": {
        "base_url": os.getenv("OPENAI_BASE_URL", "https://yibuapi.com/v1"),
        "api_key": os.getenv("OPENAI_API_KEY", ""),
        "model": os.getenv("OPENAI_MODEL", "gemini-3.1-pro-preview"),
        "max_tokens": 4096,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-32a08df7f8bd4c59814537cba9d27616",
        "model": "deepseek-v4-pro",
        "max_tokens": 8192,  # reasoning 模型，给 reasoning 留够预算
    },
}


# ───────── 测试集准备 ─────────
def load_test_set(exclude_leaked: bool = True) -> list:
    """加载测试集：冲量 + 主管意见 + 有正文。可选排除 archive 泄漏样本。"""
    records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)
    match_texts(records, DRAMA_DIR)
    pool = [
        r for r in records
        if r.table_source == "冲量"
        and r.status_source == "supervisor_opinion"
        and r.text_content
    ]
    if exclude_leaked:
        import glob
        archive_titles = set()
        for f in glob.glob(
            str(Path(__file__).resolve().parent.parent / "outputs" / "archives" / "*.json")
        ):
            archive_titles.add(json.load(open(f))["title"])
        before = len(pool)
        pool = [r for r in pool if r.title not in archive_titles]
        logger.info(f"排除 archive 泄漏样本：{before - len(pool)} 部")
    # 去重（同一标题在不同冲量表都有）
    seen = set()
    unique = []
    for r in pool:
        if r.title in seen:
            continue
        seen.add(r.title)
        unique.append(r)
    return unique


# ───────── 单次预测 ─────────
async def predict(
    client: AsyncOpenAI,
    model_name: str,
    max_tokens: int,
    handbook: str,
    record,
) -> dict | None:
    template = (PROMPT_DIR / "backtest_predict.md").read_text(encoding="utf-8")
    user_prompt = (
        template
        .replace("{handbook}", handbook)
        .replace("{title}", record.title)
        .replace("{source_type}", record.source_type or "")
        .replace("{genre}", record.genre or "")
        .replace(
            "{text_content}",
            record.text_content[:30000] if record.text_content else "正文缺失",
        )
    )
    system_prompt = "你是一位使用评审手册的剧本评审员。严格按照 JSON 格式输出。"
    t0 = time.time()
    try:
        resp = await client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - t0
        raw = resp.choices[0].message.content or ""
        if not raw:
            logger.warning(f"[{model_name}] {record.title}: empty content (max_tokens 可能不够)")
            return None
        data = extract_json(raw)
        data["_elapsed"] = round(elapsed, 1)
        return data
    except Exception as e:
        logger.error(f"[{model_name}] {record.title}: {e}")
        return None


async def run_model(
    name: str,
    cfg: dict,
    records: list,
    handbook: str,
    concurrency: int = 3,
) -> list[dict]:
    client = AsyncOpenAI(base_url=cfg["base_url"], api_key=cfg["api_key"])
    sem = asyncio.Semaphore(concurrency)

    async def task(r):
        async with sem:
            return r.title, await predict(client, cfg["model"], cfg["max_tokens"], handbook, r)

    logger.info(f"[{name}] 启动 {len(records)} 个预测任务，并发 {concurrency}")
    results = await asyncio.gather(*(task(r) for r in records))
    return [{"title": t, "pred": p} for t, p in results]


# ───────── 指标计算 ─────────
def compute_metrics(model_name: str, predictions: list[dict], truth_by_title: dict) -> dict:
    n = total_with_pred = 0
    status_hits = 0
    critical = 0
    confusion: Counter = Counter()
    score_buckets: list[int] = []
    elapsed_list: list[float] = []
    failed: list[str] = []
    by_status_dist: Counter = Counter()

    for p in predictions:
        n += 1
        if not p["pred"]:
            failed.append(p["title"])
            continue
        total_with_pred += 1
        truth = truth_by_title[p["title"]]
        pred_status = p["pred"].get("predicted_status")
        pred_score = p["pred"].get("predicted_score") or 0
        if pred_status == truth:
            status_hits += 1
        if (pred_status == "签" and truth == "拒") or (pred_status == "拒" and truth == "签"):
            critical += 1
        confusion[f"{truth}->{pred_status}"] += 1
        by_status_dist[pred_status] += 1
        score_buckets.append(pred_score)
        if "_elapsed" in p["pred"]:
            elapsed_list.append(p["pred"]["_elapsed"])

    return {
        "model": model_name,
        "n": n,
        "predicted_ok": total_with_pred,
        "failed": failed,
        "status_accuracy": round(status_hits / total_with_pred, 3) if total_with_pred else 0,
        "critical_miss_rate": round(critical / total_with_pred, 3) if total_with_pred else 0,
        "score_mean": round(sum(score_buckets) / len(score_buckets), 1) if score_buckets else 0,
        "score_min": min(score_buckets) if score_buckets else 0,
        "score_max": max(score_buckets) if score_buckets else 0,
        "elapsed_mean": round(sum(elapsed_list) / len(elapsed_list), 1) if elapsed_list else 0,
        "predicted_status_dist": dict(by_status_dist),
        "confusion_matrix": dict(confusion),
    }


def compute_agreement(preds_a: list[dict], preds_b: list[dict]) -> dict:
    by_a = {p["title"]: p["pred"] for p in preds_a}
    by_b = {p["title"]: p["pred"] for p in preds_b}
    common = set(by_a) & set(by_b)
    status_agree = 0
    score_diffs: list[int] = []
    both_failed = 0
    one_failed = 0
    for t in common:
        a, b = by_a[t], by_b[t]
        if not a and not b:
            both_failed += 1
            continue
        if not a or not b:
            one_failed += 1
            continue
        if a.get("predicted_status") == b.get("predicted_status"):
            status_agree += 1
        score_diffs.append(abs((a.get("predicted_score") or 0) - (b.get("predicted_score") or 0)))
    n_both_pred = len(common) - both_failed - one_failed
    return {
        "n_common": len(common),
        "both_failed": both_failed,
        "one_failed": one_failed,
        "n_both_predicted": n_both_pred,
        "status_agree_rate": round(status_agree / n_both_pred, 3) if n_both_pred else 0,
        "score_mae_pairwise": round(sum(score_diffs) / len(score_diffs), 1) if score_diffs else 0,
        "score_max_diff": max(score_diffs) if score_diffs else 0,
    }


# ───────── 报告 ─────────
def render_report(
    test_records: list,
    truth_by_title: dict,
    predictions_by_model: dict,
    metrics_by_model: dict,
    agreement: dict,
    handbook_version: str,
) -> str:
    lines = [
        f"# 模型对比报告：gemini-3.1-pro-preview vs deepseek-v4-pro",
        f"",
        f"> 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"> handbook: {handbook_version}",
        f"> 测试集: {len(test_records)} 部冲量剧本（主管意见为真值，已排除 archive 泄漏样本）",
        f"",
        f"## 1. 总览",
        f"",
        f"| 指标 | gemini | deepseek |",
        f"|---|---:|---:|",
    ]
    g, d = metrics_by_model["gemini"], metrics_by_model["deepseek"]
    rows = [
        ("总样本", "n"),
        ("成功预测", "predicted_ok"),
        ("Status 命中率", "status_accuracy"),
        ("严重误判率（签↔拒）", "critical_miss_rate"),
        ("预测分均值", "score_mean"),
        ("预测分区间", lambda m: f"[{m['score_min']}, {m['score_max']}]"),
        ("平均耗时(s)", "elapsed_mean"),
    ]
    for label, key in rows:
        if callable(key):
            lines.append(f"| {label} | {key(g)} | {key(d)} |")
        else:
            lines.append(f"| {label} | {g[key]} | {d[key]} |")

    lines += [
        "",
        f"## 2. 模型间一致性",
        f"",
        f"- 双方均成功预测的样本数: {agreement['n_both_predicted']}",
        f"- Status 一致率: **{agreement['status_agree_rate']:.0%}**",
        f"- 分数 MAE（两模型间）: {agreement['score_mae_pairwise']}",
        f"- 单样本最大分数差: {agreement['score_max_diff']}",
        f"- 双方都失败: {agreement['both_failed']} | 仅一方失败: {agreement['one_failed']}",
    ]

    # 预测状态分布
    lines += [
        "",
        f"## 3. 预测状态分布",
        f"",
        f"| 模型 | 签 | 改 | 拒 |",
        f"|---|---:|---:|---:|",
    ]
    truth_dist = Counter(truth_by_title.values())
    lines.append(
        f"| 真值（主管意见） | {truth_dist.get('签',0)} | {truth_dist.get('改',0)} | {truth_dist.get('拒',0)} |"
    )
    for m_name in ("gemini", "deepseek"):
        d_ = metrics_by_model[m_name]["predicted_status_dist"]
        lines.append(
            f"| {m_name} | {d_.get('签',0)} | {d_.get('改',0)} | {d_.get('拒',0)} |"
        )

    # 逐条对比
    lines += [
        "",
        f"## 4. 逐条对比",
        f"",
        f"| # | 剧本 | 真值 | gemini 状态/分 | deepseek 状态/分 | 命中(g/d) |",
        f"|--:|---|:--:|---|---|:--:|",
    ]
    by_title_g = {p["title"]: p["pred"] for p in predictions_by_model["gemini"]}
    by_title_d = {p["title"]: p["pred"] for p in predictions_by_model["deepseek"]}
    for i, r in enumerate(test_records, 1):
        gp = by_title_g.get(r.title)
        dp = by_title_d.get(r.title)
        g_str = (
            f"{gp['predicted_status']}/{gp['predicted_score']}"
            if gp else "FAIL"
        )
        d_str = (
            f"{dp['predicted_status']}/{dp['predicted_score']}"
            if dp else "FAIL"
        )
        g_hit = "✓" if gp and gp.get("predicted_status") == r.status else "✗"
        d_hit = "✓" if dp and dp.get("predicted_status") == r.status else "✗"
        lines.append(
            f"| {i} | {r.title[:30]} | {r.status} | {g_str} | {d_str} | {g_hit}/{d_hit} |"
        )

    lines += [
        "",
        f"## 5. 失败案例",
        f"",
    ]
    for m_name in ("gemini", "deepseek"):
        failed = metrics_by_model[m_name]["failed"]
        if failed:
            lines.append(f"### {m_name} ({len(failed)} 部)")
            for t in failed:
                lines.append(f"- {t}")

    return "\n".join(lines)


# ───────── 主流程 ─────────
async def main_async(args):
    test_records = load_test_set(exclude_leaked=not args.allow_leak)
    if args.n:
        test_records = test_records[: args.n]
    truth_by_title = {r.title: r.status for r in test_records}
    logger.info(f"测试集 {len(test_records)} 部")

    # 选 handbook
    handbook_path = max(
        HANDBOOK_DIR.glob("handbook_v*.md"),
        key=lambda p: int(re.search(r"_v(\d+)", p.name).group(1)),
    )
    handbook = handbook_path.read_text(encoding="utf-8")
    logger.info(f"使用 handbook: {handbook_path.name}（{len(handbook)} 字符）")

    # 并发跑两个模型
    t0 = time.time()
    gem_task = run_model("gemini", MODELS["gemini"], test_records, handbook, concurrency=args.concurrency)
    ds_task = run_model("deepseek", MODELS["deepseek"], test_records, handbook, concurrency=args.concurrency)
    gem_preds, ds_preds = await asyncio.gather(gem_task, ds_task)
    logger.info(f"双模型预测完成，总耗时 {time.time()-t0:.1f}s")

    metrics = {
        "gemini": compute_metrics("gemini", gem_preds, truth_by_title),
        "deepseek": compute_metrics("deepseek", ds_preds, truth_by_title),
    }
    agreement = compute_agreement(gem_preds, ds_preds)
    predictions = {"gemini": gem_preds, "deepseek": ds_preds}

    report = render_report(
        test_records, truth_by_title, predictions, metrics, agreement, handbook_path.name
    )

    out_dir = Path(__file__).resolve().parent.parent / "outputs" / "experiments"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    md_path = out_dir / f"compare_models_{stamp}.md"
    json_path = out_dir / f"compare_models_{stamp}.json"
    md_path.write_text(report, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "handbook": handbook_path.name,
                "test_set_titles": [r.title for r in test_records],
                "truth_by_title": truth_by_title,
                "metrics": metrics,
                "agreement": agreement,
                "predictions": predictions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n报告已保存:\n  {md_path}\n  {json_path}\n")
    print("=" * 60)
    print(report)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=None, help="只跑前 N 部（调试用）")
    p.add_argument("--allow-leak", action="store_true", help="不排除 archive 泄漏样本")
    p.add_argument("--concurrency", type=int, default=3, help="单模型并发")
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
