from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from script_rubric.config import (
    XLSX_PATH, DRAMA_DIR, PARSED_DIR, ARCHIVES_DIR, HANDBOOK_DIR,
    HOLDOUT_RATIO, HOLDOUT_SEED,
    BACKTEST_STATUS_ACCURACY, BACKTEST_RANGE_ACCURACY,
    BACKTEST_MAE_THRESHOLD, BACKTEST_CRITICAL_MISS_RATE,
)
from script_rubric.pipeline.parse_xlsx import parse_xlsx, save_parsed
from script_rubric.pipeline.match_texts import match_texts
from script_rubric.pipeline.pass1_extract import extract_all, load_all_archives
from script_rubric.pipeline.pass2_synthesize import synthesize_all
from script_rubric.pipeline.backtest import split_holdout, run_backtest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("run")


async def cmd_full(args):
    logger.info("=== Full Run ===")

    logger.info("Step 1: Parsing xlsx (with scored expansion)...")
    all_records = parse_xlsx(XLSX_PATH, include_scored=True)
    confirmed = [r for r in all_records if r.status_source == "confirmed"]
    scored_only = [r for r in all_records if r.status_source == "score_inferred"]
    logger.info(
        f"  Parsed {len(all_records)} records "
        f"(confirmed={len(confirmed)}, score_inferred={len(scored_only)})"
    )

    logger.info("Step 2: Matching text files...")
    match_result = match_texts(all_records, DRAMA_DIR)
    logger.info(f"  Matched {match_result.matched}/{match_result.total} texts")
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    (PARSED_DIR / "match_report.txt").write_text(match_result.to_report(), encoding="utf-8")
    save_parsed(all_records, PARSED_DIR / "scripts.json")

    logger.info("Step 3: Splitting holdout set (confirmed only)...")
    train_confirmed, test = split_holdout(confirmed, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)
    train = train_confirmed + scored_only
    logger.info(
        f"  Train: {len(train)} (confirmed={len(train_confirmed)}, "
        f"score_inferred={len(scored_only)}), Test: {len(test)}"
    )

    confirmed_train_titles = {r.title for r in train_confirmed}
    split_info = {
        "train_titles": [r.title for r in train],
        "test_titles": [r.title for r in test],
        "score_inferred_titles": [r.title for r in scored_only],
    }
    (PARSED_DIR / "holdout_split.json").write_text(
        json.dumps(split_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    logger.info(f"Step 4: Pass 1 extraction ({len(train)} scripts)...")
    archives = await extract_all(train, skip_existing=not args.force)
    logger.info(f"  Extracted {len(archives)} archives")

    version = args.version or 1
    logger.info(f"Step 5: Pass 2 synthesis -> handbook v{version}...")
    await synthesize_all(archives, version=version, confirmed_titles=confirmed_train_titles)
    logger.info("  Handbook and rubric generated")

    logger.info(f"Step 6: Backtesting on {len(test)} holdout scripts...")
    metrics = await run_backtest(test, version=version)
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

    records = parse_xlsx(XLSX_PATH, include_scored=True)
    confirmed = [r for r in records if r.status_source == "confirmed"]
    match_texts(records, DRAMA_DIR)
    logger.info(f"Total records: {len(records)} (confirmed={len(confirmed)})")

    existing_archives = load_all_archives()
    existing_titles = {a.title for a in existing_archives}
    new_records = [r for r in records if r.title not in existing_titles]
    logger.info(f"New records: {len(new_records)}")

    if not new_records:
        logger.info("No new records found. Nothing to do.")
        return

    new_archives = await extract_all(new_records, skip_existing=False)
    logger.info(f"Extracted {len(new_archives)} new archives")

    all_archives = existing_archives + new_archives
    confirmed_titles = {r.title for r in confirmed}
    if args.version:
        version = args.version
    else:
        existing_handbooks = list(HANDBOOK_DIR.glob("handbook_v*.md")) if HANDBOOK_DIR.exists() else []
        version = len(existing_handbooks) + 1
    logger.info(f"Re-synthesizing handbook v{version} with {len(all_archives)} total archives...")
    await synthesize_all(all_archives, version=version, confirmed_titles=confirmed_titles)

    logger.info("=== Incremental run complete ===")


async def cmd_backtest_only(args):
    version = args.version or 1
    logger.info(f"=== Backtest Only (v{version}) ===")

    records = parse_xlsx(XLSX_PATH)
    match_texts(records, DRAMA_DIR)
    _, test = split_holdout(records, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)

    metrics = await run_backtest(test, version=version)
    logger.info(
        f"Results: status={metrics.status_accuracy:.0%}, "
        f"range={metrics.range_accuracy:.0%}, mae={metrics.mae:.1f}"
    )


async def cmd_pass2_only(args):
    version = args.version or 1
    logger.info(f"=== Pass 2 Only -> v{version} ===")

    all_records = parse_xlsx(XLSX_PATH, include_scored=True)
    confirmed = [r for r in all_records if r.status_source == "confirmed"]
    scored_only = [r for r in all_records if r.status_source == "score_inferred"]
    match_texts(all_records, DRAMA_DIR)

    train_confirmed, test = split_holdout(confirmed, ratio=HOLDOUT_RATIO, seed=HOLDOUT_SEED)
    confirmed_train_titles = {r.title for r in train_confirmed}
    all_train_titles = confirmed_train_titles | {r.title for r in scored_only}
    logger.info(
        f"Holdout split: train_confirmed={len(train_confirmed)}, "
        f"score_inferred={len(scored_only)}, test={len(test)}"
    )

    all_archives = load_all_archives()
    archives = [a for a in all_archives if a.title in all_train_titles]
    skipped = len(all_archives) - len(archives)
    logger.info(
        f"Loaded {len(all_archives)} archives, using {len(archives)} (training only); "
        f"skipped {skipped} (test or unknown)"
    )

    await synthesize_all(archives, version=version, confirmed_titles=confirmed_train_titles)
    logger.info("Done")


def main():
    parser = argparse.ArgumentParser(description="Script Rubric Pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    p_full = sub.add_parser("full", help="Full pipeline run")
    p_full.add_argument("--version", type=int, default=1)
    p_full.add_argument("--force", action="store_true", help="Re-extract existing archives")

    p_inc = sub.add_parser("incremental", help="Incremental run with new data")
    p_inc.add_argument("--version", type=int, default=None)

    p_bt = sub.add_parser("backtest", help="Re-run backtest only")
    p_bt.add_argument("--version", type=int, default=1)

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
