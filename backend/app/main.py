"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import init_db
# 导入所有模型，确保 Base.metadata 包含完整表定义
import app.models  # noqa: F401
from app.routers import project_router, chapter_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时初始化数据库"""
    await init_db()
    yield


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Novel Writer API",
    description="AI 辅助小说创作平台后端接口",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件（开发环境允许所有来源）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(project_router)
app.include_router(chapter_router)


@app.get("/")
async def root():
    """根路径健康检查"""
    return {"message": "Novel Writer API", "version": "1.0.0"}
