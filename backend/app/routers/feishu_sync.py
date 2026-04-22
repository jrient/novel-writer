"""
飞书文档同步 API 路由
======================

提供手动触发同步、查看同步状态和执行日志的功能。
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.scheduled_task import (
    trigger_manual_sync,
    get_sync_history as _get_sync_history,
    get_last_sync_info,
)

router = APIRouter(prefix="/api/v1/feishu-sync", tags=["飞书文档同步"])


class SyncStatus(BaseModel):
    last_sync: dict | None
    history_count: int


class SyncTriggerResponse(BaseModel):
    success: bool
    message: str
    elapsed: float


class HistoryResponse(BaseModel):
    history: list


@router.get("/status", response_model=SyncStatus)
async def get_sync_status():
    """获取飞书同步状态：最近一次执行信息和历史记录数量"""
    last = get_last_sync_info()
    return {
        "last_sync": last,
        "history_count": len(_get_sync_history(limit=999)),
    }


@router.get("/history", response_model=HistoryResponse)
async def get_sync_history_api(limit: int = 10):
    """获取同步执行历史"""
    if limit > 50:
        limit = 50
    return {"history": _get_sync_history(limit=limit)}


@router.post("/trigger", response_model=SyncTriggerResponse)
async def trigger_sync():
    """手动触发一次飞书文档同步"""
    result = await trigger_manual_sync()
    if result["success"]:
        return {
            "success": True,
            "message": result["message"],
            "elapsed": result["elapsed"],
        }
    else:
        raise HTTPException(status_code=500, detail=result["message"])
