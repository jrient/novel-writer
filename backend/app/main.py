"""
FastAPI 应用入口
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.database import init_db
from app.middleware import RequestIDMiddleware, RequestLoggingMiddleware
# 导入所有模型，确保 Base.metadata 包含完整表定义
import app.models  # noqa: F401
from app.routers import (
    auth_router,
    project_router,
    chapter_router,
    character_router,
    worldbuilding_router,
    outline_router,
    ai_router,
    ai_config_router,
    ai_batch_router,
    export_router,
    reference_router,
    search_router,
    knowledge_router,
    wizard_router,
    event_router,
    note_router,
    admin_router,
    drama_router,
    expansion_router,
)
from app.routers.rubric_pipeline import router as rubric_pipeline_router
from app.services.scheduled_task import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库、启动定时任务"""
    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()


# 配置日志
import sys

# 创建日志格式（兼容没有 request_id 的情况）
class RequestIdFilter(logging.Filter):
    """为日志记录添加 request_id 字段"""
    def filter(self, record):
        if not hasattr(record, 'request_id'):
            record.request_id = '-'
        return True

# 配置根日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 为所有日志记录器添加 request_id 过滤器
for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())

# 创建 API 专用日志记录器
api_logger = logging.getLogger("api_logger")
api_logger.setLevel(logging.INFO)
api_logger.addFilter(RequestIdFilter())

logger = logging.getLogger(__name__)


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Novel Writer API",
    description="AI 辅助小说创作平台后端接口",
    version="1.0.0",
    lifespan=lifespan,
)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器，统一错误返回格式"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后再试"}
    )


# CORS 中间件 - 使用环境变量配置允许的来源
allowed_origins = settings.ALLOWED_ORIGINS.split(",") if settings.ALLOWED_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 请求 ID 中间件
app.add_middleware(RequestIDMiddleware)

# 请求日志中间件
app.add_middleware(RequestLoggingMiddleware)

# 注册路由
app.include_router(auth_router)
app.include_router(project_router)
app.include_router(chapter_router)
app.include_router(character_router)
app.include_router(worldbuilding_router)
app.include_router(outline_router)
app.include_router(ai_router)
app.include_router(ai_config_router)
app.include_router(ai_batch_router)
app.include_router(export_router)
app.include_router(reference_router)
app.include_router(search_router)
app.include_router(knowledge_router)
app.include_router(wizard_router)
app.include_router(event_router)
app.include_router(note_router)
app.include_router(admin_router)
app.include_router(drama_router)
app.include_router(expansion_router)
app.include_router(rubric_pipeline_router)


@app.get("/")
async def root():
    """根路径健康检查"""
    return {"status": "ok"}


@app.get("/.env")
async def block_env():
    """阻止 .env 文件扫描"""
    return {"status": "not found"}