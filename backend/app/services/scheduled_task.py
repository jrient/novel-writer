"""
定时任务服务 - APScheduler 集成
=================================

每天凌晨2点自动执行飞书文档拉取任务。
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger("api_logger")

# ── 飞书文档脚本路径 ──────────────────────────────────────────────────────────
# 在 Docker 容器内: /app/app/services/scheduled_task.py → project root = /app
# 在本地开发:        /path/novel-writer/backend/app/services/... → project root
# 优先用环境变量，否则向上查找直到找到 data/ 目录


def _find_project_root() -> str:
    """从当前文件所在目录向上查找，直到找到包含 data/ 子目录的路径"""
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):  # 最多向上 8 层
        if os.path.isdir(os.path.join(current, "data")):
            return current
        parent = os.path.dirname(current)
        if parent == current:  # 已到根目录
            break
        current = parent
    # fallback: 默认向上 3 层
    return os.path.join(os.path.dirname(__file__), "..", "..", "..")


PROJECT_ROOT = os.environ.get("PROJECT_ROOT", _find_project_root())
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
if DATA_DIR not in sys.path:
    sys.path.insert(0, DATA_DIR)

# ── 执行日志存储 ───────────────────────────────────────────────────────────────
# 日志存储在 data/feishu_sync_logs/ 目录
LOG_DIR = os.path.join(DATA_DIR, "feishu_sync_logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "sync_history.json")

# 最多保留 50 条历史记录
MAX_HISTORY = 50


def _load_history() -> list:
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_history(entry: dict):
    history = _load_history()
    history.insert(0, entry)  # 最新的在前面
    history = history[:MAX_HISTORY]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def get_sync_history(limit: int = 10) -> list:
    """获取最近 N 条执行记录"""
    return _load_history()[:limit]


def get_last_sync_info() -> Optional[dict]:
    """获取最近一次执行信息"""
    history = _load_history()
    return history[0] if history else None


# ── 核心同步函数 ───────────────────────────────────────────────────────────────

async def run_feishu_sync(trigger: str = "scheduled"):
    """执行飞书文档同步任务"""
    # Force fresh import to pick up file changes
    import importlib  # noqa: E402
    import data.get_feishu_doc as feishu_module  # noqa: E402
    importlib.reload(feishu_module)
    feishu_run_sync = feishu_module.run_sync

    log_lines = []

    def log_callback(msg, **kwargs):
        log_lines.append(msg)
        logger.info(f"[FeishuSync] {msg}")

    start_time = datetime.now()
    logger.info("开始执行飞书文档同步任务...")

    try:
        result = await asyncio.to_thread(feishu_run_sync, log_callback)

        end_time = datetime.now()
        entry = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "success": result["success"],
            "message": result["message"],
            "elapsed": round(result["elapsed"], 1),
            "files_count": len(result.get("files", [])),
            "error": result.get("error"),
            "trigger": trigger,
            "log_summary": "\n".join(log_lines[-10:]),  # 最后10行摘要
        }

        _save_history(entry)

        if result["success"]:
            logger.info(f"飞书同步成功: {result['message']}")
            # 自动触发 rubric pipeline（异步，不影响 sync 结果）
            asyncio.create_task(_trigger_pipeline_after_sync())
        else:
            logger.error(f"飞书同步失败: {result['message']}")

        return entry

    except Exception as e:
        end_time = datetime.now()
        entry = {
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "success": False,
            "message": f"同步异常: {str(e)}",
            "elapsed": round((end_time - start_time).total_seconds(), 1),
            "error": str(e),
            "trigger": trigger,
            "log_summary": "\n".join(log_lines[-5:]),
        }
        _save_history(entry)
        logger.error(f"飞书同步异常: {e}", exc_info=True)
        return entry


# ── 调度器管理 ─────────────────────────────────────────────────────────────────

scheduler: Optional[AsyncIOScheduler] = None


def init_scheduler():
    """初始化并配置调度器"""
    global scheduler

    if scheduler is not None:
        return

    scheduler = AsyncIOScheduler()

    # 每天凌晨2点执行
    scheduler.add_job(
        run_feishu_sync,
        trigger=CronTrigger(hour=2, minute=0, timezone="Asia/Shanghai"),
        id="feishu_daily_sync",
        name="每日飞书文档同步",
        replace_existing=True,
        max_instances=1,  # 防止重叠执行
    )

    logger.info("定时任务调度器已初始化: 每天 02:00 (Asia/Shanghai) 执行飞书同步")


async def start_scheduler():
    """启动调度器"""
    init_scheduler()
    if scheduler and not scheduler.running:
        scheduler.start()
        next_run = scheduler.get_job("feishu_daily_sync")
        if next_run:
            logger.info(f"下次执行时间: {next_run.next_run_time}")


async def stop_scheduler():
    """关闭调度器"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已关闭")


async def trigger_manual_sync():
    """手动触发一次同步"""
    return await run_feishu_sync(trigger="manual")


async def _trigger_pipeline_after_sync():
    """飞书同步完成后触发 rubric pipeline，失败不影响 sync"""
    try:
        from app.services.rubric_pipeline_service import trigger_pipeline_after_sync
        await trigger_pipeline_after_sync()
    except Exception as e:
        logger.error(f"Rubric pipeline trigger error: {e}", exc_info=True)
