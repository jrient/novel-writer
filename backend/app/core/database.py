from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

# 配置数据库引擎 - SQLite 和 PostgreSQL 使用不同配置
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite 不支持连接池参数
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
    )
else:
    # PostgreSQL 配置连接池
    # 低端服务器（≈1.6Gi 物理内存）瘦身：每条 PG 连接驻留 ~10MB，
    # 20+10 满载即吃掉 ~300MB。adaptation 改写并发已限 2，
    # 加上 SSE/普通请求峰值 ~3 条连接即可覆盖；溢出关掉避免突发风暴。
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=3,
        max_overflow=0,
        pool_recycle=3600,
        pool_pre_ping=True,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 增量迁移：为已有表添加 owner_id 列（如果不存在）
        if not settings.DATABASE_URL.startswith("sqlite"):
            from sqlalchemy import text
            for table in ("reference_novels", "knowledge_entries"):
                result = await conn.execute(text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name='{table}' AND column_name='owner_id'"
                ))
                if not result.fetchone():
                    await conn.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN owner_id INTEGER REFERENCES users(id)"
                    ))
                    await conn.execute(text(
                        f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON {table}(owner_id)"
                    ))
            # prose_projects: add script_content, make script_project_id nullable
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='prose_projects' AND column_name='script_content'"
            ))
            if not result.fetchone():
                await conn.execute(text(
                    "ALTER TABLE prose_projects ADD COLUMN script_content TEXT"
                ))
                await conn.execute(text(
                    "ALTER TABLE prose_projects ALTER COLUMN script_project_id DROP NOT NULL"
                ))
