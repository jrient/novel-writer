"""
剧本评审 Pipeline 服务
======================
在飞书同步完成后自动触发 script_rubric pipeline，
以子进程方式运行（隔离 LLM 调用和 asyncio 事件循环）。
"""
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("api_logger")


def _find_project_root() -> str:
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(current, "data")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.path.join(os.path.dirname(__file__), "..", "..", "..")


PROJECT_ROOT = os.environ.get("PROJECT_ROOT", _find_project_root())
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "pipeline_logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "pipeline_history.json")
MAX_HISTORY = 50

# 默认超时 60 分钟（增量模式可能需要较多 LLM 调用）
DEFAULT_TIMEOUT = 3600


def check_llm_config() -> dict:
    """检查 LLM 配置是否就绪"""
    return {
        "api_base": os.getenv("OPENAI_BASE_URL"),
        "api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("RUBRIC_MODEL") or os.getenv("OPENAI_MODEL", "not set"),
    }


def _detect_next_handbook_version() -> int:
    handbook_dir = Path(PROJECT_ROOT) / "script_rubric" / "outputs" / "handbook"
    if not handbook_dir.exists():
        return 1
    existing = [int(m.group(1)) for f in handbook_dir.glob("handbook_v*.md")
                if (m := re.search(r"v(\d+)", f.stem))]
    return max(existing, default=0) + 1


def _detect_latest_handbook_version() -> Optional[str]:
    handbook_dir = Path(PROJECT_ROOT) / "script_rubric" / "outputs" / "handbook"
    if not handbook_dir.exists():
        return None
    files = sorted(handbook_dir.glob("handbook_v*.md"),
                   key=lambda f: int(re.search(r"v(\d+)", f.stem).group(1)))
    if not files:
        return None
    m = re.search(r"v(\d+)", files[-1].stem)
    return f"v{m.group(1)}" if m else None


def _parse_backtest_metrics(stdout_text: str) -> Optional[dict]:
    """从 stdout 提取 backtest 指标"""
    metrics = {}
    for pattern, key in [
        (r"Status accuracy: ([\d.]+)%", "status_accuracy"),
        (r"Range accuracy: ([\d.]+)%", "range_accuracy"),
        (r"MAE: ([\d.]+)", "mae"),
        (r"Critical miss rate: ([\d.]+)%", "critical_miss_rate"),
    ]:
        m = re.search(pattern, stdout_text)
        if m:
            metrics[key] = float(m.group(1))
    return metrics if metrics else None


def _load_history() -> list:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_history(entry: dict):
    history = _load_history()
    history.insert(0, entry)
    history = history[:MAX_HISTORY]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_pipeline_history(limit: int = 10) -> list:
    return _load_history()[:limit]


def get_last_pipeline_run() -> Optional[dict]:
    history = _load_history()
    return history[0] if history else None


async def run_pipeline(mode: str = "incremental", force: bool = False,
                       version: Optional[int] = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    以子进程方式运行 script_rubric pipeline。

    Args:
        mode: "incremental" (仅新记录) | "full" (全量重跑)
        force: 是否强制重新提取已有档案
        version: 指定版本号，不指定则自动计算下一个
        timeout: 超时秒数，默认 3600

    Returns:
        执行结果字典
    """
    start_time = datetime.now()
    entry = {
        "start_time": start_time.isoformat(),
        "end_time": None,
        "success": False,
        "mode": mode,
        "message": "",
        "elapsed": 0,
        "new_archives": 0,
        "handbook_version": None,
        "backtest_metrics": None,
        "error": None,
    }

    if not version:
        version = _detect_next_handbook_version()

    script_path = os.path.join(PROJECT_ROOT, "script_rubric", "pipeline", "run.py")
    cmd = [sys.executable, script_path, mode, "--version", str(version)]
    if force:
        cmd.append("--force")

    logger.info(f"Starting rubric pipeline: {' '.join(cmd)}")

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=PROJECT_ROOT,
            env={**os.environ},
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )

        stdout_text = stdout.decode("utf-8", errors="replace")
        stderr_text = stderr.decode("utf-8", errors="replace")

        new_archives_match = re.search(r"Extracted (\d+) new archives", stdout_text)
        handbook_v = _detect_latest_handbook_version()
        backtest_metrics = _parse_backtest_metrics(stdout_text)

        elapsed = round((datetime.now() - start_time).total_seconds(), 1)
        entry["end_time"] = datetime.now().isoformat()
        entry["elapsed"] = elapsed
        entry["success"] = process.returncode == 0
        entry["new_archives"] = int(new_archives_match.group(1)) if new_archives_match else 0
        entry["handbook_version"] = handbook_v
        entry["backtest_metrics"] = backtest_metrics
        entry["stdout_summary"] = stdout_text[-1000:] if stdout_text else ""

        if process.returncode == 0:
            entry["message"] = f"Pipeline {mode} 完成，版本 v{version}，耗时 {elapsed}s"
            if backtest_metrics:
                sa = backtest_metrics.get("status_accuracy", 0)
                entry["message"] += f" | 状态命中率 {sa:.0%}"
            logger.info(f"Pipeline success: {entry['message']}")
        else:
            entry["message"] = f"Pipeline 退出码 {process.returncode}"
            entry["error"] = stderr_text[:2000] if stderr_text else "unknown error"
            logger.error(f"Pipeline failed: {entry['error']}")

    except asyncio.TimeoutError:
        elapsed = round((datetime.now() - start_time).total_seconds(), 1)
        entry["end_time"] = datetime.now().isoformat()
        entry["elapsed"] = elapsed
        entry["message"] = f"Pipeline 超时（{timeout}s）"
        entry["error"] = f"timeout after {timeout}s"
        logger.error("Pipeline timed out, killing subprocess...")
        try:
            process.kill()
            await process.wait()
        except ProcessLookupError:
            pass  # already exited
        logger.warning("Pipeline subprocess terminated")

    except Exception as e:
        elapsed = round((datetime.now() - start_time).total_seconds(), 1)
        entry["end_time"] = datetime.now().isoformat()
        entry["elapsed"] = elapsed
        entry["message"] = f"Pipeline 异常: {str(e)}"
        entry["error"] = str(e)
        logger.error(f"Pipeline exception: {e}", exc_info=True)

    _save_history(entry)
    return entry


async def trigger_pipeline_after_sync():
    """飞书同步完成后异步触发 pipeline，失败不影响 sync 结果"""
    try:
        logger.info("Auto-triggering rubric pipeline (incremental)...")
        result = await run_pipeline(mode="incremental")
        if result["success"]:
            logger.info(
                f"Rubric pipeline completed: "
                f"handbook={result['handbook_version']}, "
                f"new_archives={result['new_archives']}, "
                f"elapsed={result['elapsed']}s"
            )
        else:
            logger.warning(
                f"Rubric pipeline failed: {result['message']} "
                f"(sync was successful, this is non-critical)"
            )
    except Exception as e:
        logger.error(f"Rubric pipeline trigger error: {e}", exc_info=True)
