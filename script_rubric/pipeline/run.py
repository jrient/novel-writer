from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from script_rubric.config import (
    BITABLE_RUBRIC_JSON, DRAMA_DIR, PARSED_DIR, ARCHIVES_DIR, HANDBOOK_DIR,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
    BACKTEST_N_SAMPLES, BACKTEST_TEMPERATURE,
    STATUS_SOURCES_HIGH_CONF,
)
from script_rubric.models import ScriptRecord
from script_rubric.pipeline.parse_bitable import parse_bitable_json
from script_rubric.pipeline.match_texts import match_texts
from script_rubric.pipeline.pass1_extract import extract_all, load_all_archives
from script_rubric.pipeline.pass2_synthesize import synthesize_all
from script_rubric.pipeline.backtest import run_backtest, split_holdout


def _split_records(
    records: list[ScriptRecord], mode: str
) -> tuple[list[ScriptRecord], list[ScriptRecord], str]:
    """根据 mode 划分 train/test，返回 (train, test, strategy_label)。

    - table: 精品=train, 冲量=test（默认）
    - stratified: 按 status 分层随机划分 (ratio=0.2, seed=42)
    """
    if mode == "stratified":
        train, test = split_holdout(records, ratio=0.2, seed=42)
        return train, test, "stratified: stratified_holdout(ratio=0.2, seed=42)"
    train = [r for r in records if r.table_source == "精品"]
    test = [r for r in records if r.table_source == "冲量"]
    return train, test, "table_based: 精品=train, 冲量=test"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run")


async def cmd_full(args):
    logger.info("=== Full Run ===")

    logger.info("Step 1: Parsing bitable JSON (with scored expansion)...")
    if not BITABLE_RUBRIC_JSON.exists():
        logger.error(f"数据文件不存在: {BITABLE_RUBRIC_JSON}")
        logger.error("请先运行: python -m script_rubric.feishu.sync_bitable <bitable_url>")
        return
    all_records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)

    train, test, strategy_label = _split_records(all_records, args.split)
    logger.info(
        f"  Parsed {len(all_records)} records "
        f"({strategy_label}, train={len(train)}, test={len(test)})"
    )

    logger.info("Step 2: Matching text files...")
    match_result = match_texts(all_records, DRAMA_DIR)
    logger.info(f"  Matched {match_result.matched}/{match_result.total} texts")
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    (PARSED_DIR / "match_report.txt").write_text(match_result.to_report(), encoding="utf-8")
    parsed_data = [r.model_dump() for r in all_records]
    (PARSED_DIR / "scripts.json").write_text(
        json.dumps(parsed_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    split_info = {
        "train_titles": [r.title for r in train],
        "test_titles": [r.title for r in test],
        "split_strategy": strategy_label,
    }
    (PARSED_DIR / "holdout_split.json").write_text(
        json.dumps(split_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Step 3: Pass 1 extraction ({len(train)} train scripts)...")
    await extract_all(train, skip_existing=not args.force)

    # 载入磁盘上全部 archive 作为历史训练池（包含本轮提取 + 历史累积）
    all_archives = load_all_archives()
    confirmed_titles = {
        a.title for a in all_archives if a.status_source in STATUS_SOURCES_HIGH_CONF
    }
    inferred_count = len(all_archives) - len(confirmed_titles)
    logger.info(f"  Training pool: {len(all_archives)} archives (confirmed={len(confirmed_titles)}, inferred={inferred_count})")

    version = args.version or 1
    logger.info(f"Step 4: Pass 2 synthesis -> handbook v{version}...")
    await synthesize_all(all_archives, version=version, confirmed_titles=confirmed_titles)
    logger.info("  Handbook and rubric generated")

    logger.info(f"Step 5: Backtesting on {len(test)} 冲量 scripts...")
    metrics = await run_backtest(
        test, version=version,
        n_samples=args.n_samples, temperature=args.temperature,
    )
    logger.info(f"  Status accuracy: {metrics.status_accuracy:.0%}")
    logger.info(f"  Range accuracy: {metrics.range_accuracy:.0%}")
    logger.info(f"  MAE: {metrics.mae:.1f}")
    logger.info(f"  Critical miss rate: {metrics.critical_miss_rate:.0%}")

    all_pass = all([
        metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY,
        metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY,
        metrics.mae <= BACKTEST_MAE_THRESHOLD,
        metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE,
    ])

    if all_pass:
        logger.info("=== PASS: Handbook meets all thresholds ===")
    else:
        logger.warning("=== FAIL: Handbook did not meet thresholds ===")


async def cmd_incremental(args):
    logger.info("=== Incremental Run ===")

    if not BITABLE_RUBRIC_JSON.exists():
        logger.error(f"数据文件不存在: {BITABLE_RUBRIC_JSON}")
        logger.error("请先运行: python -m script_rubric.feishu.sync_bitable <bitable_url>")
        return

    records = parse_bitable_json(BITABLE_RUBRIC_JSON, include_scored=True)
    train, test, strategy_label = _split_records(records, args.split)
    match_texts(records, DRAMA_DIR)
    logger.info(f"Total records: {len(records)} ({strategy_label}, train={len(train)}, test={len(test)})")

    existing_archives = load_all_archives()
    existing_titles = {a.title for a in existing_archives}
    new_records = [r for r in train if r.title not in existing_titles]
    logger.info(f"New records: {len(new_records)}")

    if new_records:
        new_archives = await extract_all(new_records, skip_existing=False)
        logger.info(f"Extracted {len(new_archives)} new archives")
        all_archives = existing_archives + new_archives
    else:
        all_archives = existing_archives
        logger.info("No new records to extract; reusing existing archives")

    # archives 是历史训练池：所有曾被 Pass1 合法提取的剧本，无论当前是否仍在 bitable
    # 仅将编辑确认状态的剧本视为 confirmed，推断状态的降权
    confirmed_titles = {
        a.title for a in all_archives if a.status_source in STATUS_SOURCES_HIGH_CONF
    }

    if args.version:
        version = args.version
    else:
        existing_handbooks = list(HANDBOOK_DIR.glob("handbook_v*.md")) if HANDBOOK_DIR.exists() else []
        version = len(existing_handbooks) + 1
    logger.info(
        f"Re-synthesizing handbook v{version} with {len(all_archives)} archives "
        f"({len(existing_archives)} existing + {len(all_archives) - len(existing_archives)} new)"
    )
    await synthesize_all(all_archives, version=version, confirmed_titles=confirmed_titles)

    logger.info(f"Backtesting on {len(test)} 冲量 scripts...")
    metrics = await run_backtest(
        test, version=version,
        n_samples=args.n_samples, temperature=args.temperature,
    )
    logger.info(f"  Status accuracy: {metrics.status_accuracy:.0%}")
    logger.info(f"  Range accuracy: {metrics.range_accuracy:.0%}")
    logger.info(f"  MAE: {metrics.mae:.1f}")
    logger.info(f"  Critical miss rate: {metrics.critical_miss_rate:.0%}")

    all_pass = all([
        metrics.status_accuracy >= BACKTEST_STATUS_ACCURACY,
        metrics.range_accuracy >= BACKTEST_RANGE_ACCURACY,
        metrics.mae <= BACKTEST_MAE_THRESHOLD,
        metrics.critical_miss_rate <= BACKTEST_CRITICAL_MISS_RATE,
    ])

    if all_pass:
        logger.info("=== PASS: Handbook meets all thresholds ===")
    else:
        logger.warning("=== FAIL: Handbook did not meet thresholds ===")

    logger.info("=== Incremental run complete ===")


async def cmd_backtest_only(args):
    version = args.version or 1
    logger.info(f"=== Backtest Only (v{version}, split={args.split}) ===")

    if not BITABLE_RUBRIC_JSON.exists():
        logger.error(f"数据文件不存在: {BITABLE_RUBRIC_JSON}")
        return

    records = parse_bitable_json(BITABLE_RUBRIC_JSON)
    match_texts(records, DRAMA_DIR)

    if args.split == "labeled":
        # Labeled-only Test Set：仅取「精品」中同时具备 mean_score(ground truth) 与 text_file 的记录
        # 用于绕开「冲量表无数字打分」的设计陷阱（aafc5f3 引入的 silent failure mode）
        # 同 title 多源去重：按 mean_score 降序保留每个 title 的一份（多源时取分高的版本）
        candidates = [
            r for r in records
            if r.table_source == "精品" and r.mean_score is not None and r.text_file
        ]
        seen: dict[str, ScriptRecord] = {}
        for r in sorted(candidates, key=lambda x: x.mean_score, reverse=True):
            seen.setdefault(r.title, r)
        test = list(seen.values())
        logger.info(
            f"Test set (labeled, 精品 with mean_score+text_file, deduped by title): "
            f"{len(test)} scripts (from {len(candidates)} raw)"
        )
    elif args.split == "stratified":
        _train, test = split_holdout(records, ratio=0.2, seed=42)
        logger.info(f"Test set (stratified, ratio=0.2 seed=42): {len(test)} scripts")
    else:
        test = [r for r in records if r.table_source == "冲量"]
        logger.info(f"Test set (table=冲量, legacy): {len(test)} scripts")

    if not test:
        logger.error("Test set 为空，终止 backtest")
        return

    metrics = await run_backtest(
        test, version=version,
        n_samples=args.n_samples, temperature=args.temperature,
    )
    logger.info(
        f"Results: status={metrics.status_accuracy:.0%}, "
        f"range={metrics.range_accuracy:.0%}, mae={metrics.mae:.1f}"
    )


async def cmd_pass2_only(args):
    version = args.version or 1
    logger.info(f"=== Pass 2 Only -> v{version} ===")

    # archives 是历史信任的训练池（每个 archive 都是过去合法精品/冲量签的 Pass1 产物）
    # 不再按当前 bitable 的 train_titles 过滤，避免飞书表删改导致历史训练数据丢失
    archives = load_all_archives()
    if not archives:
        logger.error("没有可用 archive，请先运行 full 或 incremental")
        return
    confirmed_titles = {a.title for a in archives}
    logger.info(f"Training pool (archives): {len(archives)} parts (all treated as confirmed)")

    await synthesize_all(archives, version=version, confirmed_titles=confirmed_titles)
    logger.info("Done")


def main():
    parser = argparse.ArgumentParser(description="Script Rubric Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    def _add_backtest_args(p):
        p.add_argument("--n-samples", type=int, default=BACKTEST_N_SAMPLES,
                       dest="n_samples",
                       help="每条记录的采样次数；>1 时启用聚合（请同步上调 --temperature）")
        p.add_argument("--temperature", type=float, default=BACKTEST_TEMPERATURE,
                       help="LLM 采样温度；多样本聚合时建议 0.3-0.5")

    p_full = sub.add_parser("full", help="Full pipeline run")
    p_full.add_argument("--version", type=int, default=1)
    p_full.add_argument("--force", action="store_true", help="Re-extract existing archives")
    p_full.add_argument("--split", choices=["table", "stratified"], default="table",
                        help="Train/test split strategy: table (精品/冲量) or stratified (按状态分层随机)")
    _add_backtest_args(p_full)

    p_inc = sub.add_parser("incremental", help="Incremental run with new data")
    p_inc.add_argument("--split", choices=["table", "stratified"], default="table",
                       help="Train/test split strategy")
    p_inc.add_argument("--version", type=int, default=None)
    _add_backtest_args(p_inc)

    p_bt = sub.add_parser("backtest", help="Re-run backtest only")
    p_bt.add_argument("--version", type=int, default=1)
    p_bt.add_argument(
        "--split", choices=["table", "stratified", "labeled"], default="labeled",
        help="Test set 选择：labeled(默认,精品里有 ground truth) / stratified(分层holdout) / table(legacy 仅冲量)",
    )
    _add_backtest_args(p_bt)

    p_p2 = sub.add_parser("pass2", help="Re-run Pass 2 only")
    p_p2.add_argument("--version", type=int, default=1)

    args = parser.parse_args()

    cmd_map = {
        "full": cmd_full,
        "incremental": cmd_incremental,
        "backtest": cmd_backtest_only,
        "pass2": cmd_pass2_only,
    }

    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()
