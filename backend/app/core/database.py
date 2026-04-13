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
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_size=20,           # 核心连接数
        max_overflow=10,        # 最大溢出连接数
        pool_recycle=3600,      # 连接回收时间（秒）
        pool_pre_ping=True,     # 自动心跳检测，防止连接断开
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
