"""
定时任务服务 - APScheduler 空壳
================================

保留调度器基础设施，但已移除飞书同步任务。
飞书多维表格数据通过 CLI (data/sync_bitable.py) 手动同步。
"""

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("api_logger")

# ── 调度器管理 ─────────────────────────────────────────────────────────────────

scheduler: Optional[AsyncIOScheduler] = None


def init_scheduler():
    """初始化调度器（目前无定时任务）"""
    global scheduler
    if scheduler is not None:
        return
    scheduler = AsyncIOScheduler()
    logger.info("定时任务调度器已初始化（当前无定时任务）")


async def start_scheduler():
    """启动调度器"""
    init_scheduler()
    if scheduler and not scheduler.running:
        scheduler.start()
        logger.info("定时任务调度器已启动")


async def stop_scheduler():
    """关闭调度器"""
    global scheduler
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务调度器已关闭")
