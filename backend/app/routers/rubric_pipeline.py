"""
剧本评审 Pipeline API 路由
===========================
手动触发 pipeline、查看运行历史和当前状态。
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.services.rubric_pipeline_service import (
    run_pipeline,
    get_pipeline_history,
    get_last_pipeline_run,
    check_llm_config,
)
from app.services.handbook_provider import get_handbook

router = APIRouter(prefix="/api/v1/rubric-pipeline", tags=["剧本评审Pipeline"])


class PipelineStatus(BaseModel):
    last_run: Optional[dict]
    handbook_version: str
    handbook_loaded: bool
    llm_config: dict
    history_count: int


class PipelineTriggerRequest(BaseModel):
    mode: str = "incremental"
    force: bool = False
    version: Optional[int] = None


class PipelineTriggerResponse(BaseModel):
    success: bool
    message: str
    elapsed: float
    handbook_version: Optional[str]
    backtest_metrics: Optional[dict]


@router.get("/status", response_model=PipelineStatus)
async def get_pipeline_status():
    """查看 pipeline 状态：最近一次运行、handbook 版本、LLM 配置"""
    last = get_last_pipeline_run()
    handbook = get_handbook()
    return {
        "last_run": last,
        "handbook_version": handbook.version,
        "handbook_loaded": handbook.is_loaded(),
        "llm_config": check_llm_config(),
        "history_count": len(get_pipeline_history(limit=999)),
    }


@router.get("/history")
async def get_pipeline_history_api(limit: int = Query(10, le=50)):
    """获取 pipeline 执行历史"""
    return {"history": get_pipeline_history(limit=limit)}


@router.post("/trigger", response_model=PipelineTriggerResponse)
async def trigger_pipeline_api(body: PipelineTriggerRequest):
    """
    手动触发 pipeline。
    - mode="incremental": 仅处理新记录（推荐）
    - mode="full": 全量重跑（含 --force 可重新提取已有档案）
    """
    if body.mode not in ("incremental", "full"):
        raise HTTPException(status_code=400, detail="mode 必须是 incremental 或 full")

    llm = check_llm_config()
    if not llm["api_key_set"]:
        raise HTTPException(
            status_code=503,
            detail="LLM API key 未配置，无法运行 pipeline。请设置 OPENAI_API_KEY 环境变量。"
        )

    result = await run_pipeline(
        mode=body.mode,
        force=body.force,
        version=body.version,
    )

    if result["success"]:
        return {
            "success": True,
            "message": result["message"],
            "elapsed": result["elapsed"],
            "handbook_version": result["handbook_version"],
            "backtest_metrics": result["backtest_metrics"],
        }
    else:
        raise HTTPException(status_code=500, detail=result["message"])


@router.post("/reload-handbook")
async def reload_handbook():
    """
    手动重新加载 handbook（新版本生成后强制刷新缓存）。
    """
    handbook = get_handbook()
    old_version = handbook.version
    handbook.reload()
    return {
        "old_version": old_version,
        "new_version": handbook.version,
        "reloaded": old_version != handbook.version,
    }
