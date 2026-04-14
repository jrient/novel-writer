"""AI 配置路由 - 独立于项目（GET /api/v1/ai/config）"""
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.ai import AIConfigResponse
from app.services.ai_service import AIService

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


@router.get("/config", response_model=AIConfigResponse)
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
    actual_default = AIService._get_available_provider(settings.DEFAULT_AI_PROVIDER)

    return AIConfigResponse(
        default_provider=actual_default,
        available_providers=available,
        models=models,
    )
