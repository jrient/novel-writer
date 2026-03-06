"""
AI 路由
处理 AI 写作辅助的 SSE 流式请求
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.worldbuilding import WorldbuildingEntry
from app.schemas.ai import AIGenerateRequest, AIConfigResponse
from app.services.ai_service import AIService

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/ai",
    tags=["ai"],
)


@router.post("/generate")
async def ai_generate(
    project_id: int,
    payload: AIGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    AI 流式生成内容
    返回 SSE (Server-Sent Events) 流
    """
    # 验证项目存在
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 获取上下文：角色和世界观
    chars_result = await db.execute(
        select(Character).where(Character.project_id == project_id).limit(10)
    )
    characters = [
        {"name": c.name, "role_type": c.role_type, "personality": c.personality_traits or ""}
        for c in chars_result.scalars().all()
    ]

    world_result = await db.execute(
        select(WorldbuildingEntry).where(WorldbuildingEntry.project_id == project_id).limit(10)
    )
    worldbuilding = [
        {"name": w.title, "description": w.content or "", "category": w.category}
        for w in world_result.scalars().all()
    ]

    # 如果指定了章节，获取章节内容作为补充
    content = payload.content
    if payload.chapter_id and not content:
        chapter_result = await db.execute(
            select(Chapter).where(
                Chapter.id == payload.chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = chapter_result.scalar_one_or_none()
        if chapter:
            content = chapter.content or ""

    return StreamingResponse(
        AIService.generate_stream(
            action=payload.action,
            content=content,
            provider=payload.provider,
            title=project.title,
            genre=project.genre or "",
            description=project.description or "",
            question=payload.question or "",
            characters=characters,
            worldbuilding=worldbuilding,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# 独立路由（不依赖项目）
config_router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@config_router.get("/config", response_model=AIConfigResponse)
async def get_ai_config():
    """获取 AI 配置信息"""
    available = []
    models = {}

    if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY not in ("sk-xxx", "", None):
        available.append("openai")
        models["openai"] = settings.OPENAI_MODEL

    if settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None):
        available.append("anthropic")
        models["anthropic"] = settings.ANTHROPIC_MODEL

    available.append("ollama")
    models["ollama"] = settings.OLLAMA_MODEL

    # 演示模式始终可用
    available.append("demo")
    models["demo"] = "built-in"

    # 如果没有真实 provider 可用，默认使用 demo
    from app.services.ai_service import AIService
    actual_default = AIService._get_available_provider(settings.DEFAULT_AI_PROVIDER)

    return AIConfigResponse(
        default_provider=actual_default,
        available_providers=available,
        models=models,
    )
