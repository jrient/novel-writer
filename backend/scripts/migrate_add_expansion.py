"""
数据库迁移脚本 - 添加扩写模块相关表
创建: expansion_projects, expansion_segments
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import Base, engine

# 导入模型确保 metadata 已注册
import app.models  # noqa: F401


EXPANSION_TABLES = ["expansion_projects", "expansion_segments"]


async def table_exists(conn, table_name: str) -> bool:
    """检查表是否存在（兼容 SQLite 和 PostgreSQL）"""
    if engine.url.drivername.startswith("sqlite"):
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": table_name},
        )
        return result.fetchone() is not None
    else:
        # PostgreSQL
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname='public' AND tablename=:name"
            ),
            {"name": table_name},
        )
        return result.fetchone() is not None


async def migrate_add_expansion():
    """创建扩写模块所需的两张新表（如果不存在）"""
    async with engine.begin() as conn:
        existing = []
        missing = []

        for table_name in EXPANSION_TABLES:
            if await table_exists(conn, table_name):
                existing.append(table_name)
            else:
                missing.append(table_name)

        if existing:
            print(f"已存在的表（跳过）: {', '.join(existing)}")

        if not missing:
            print("所有扩写模块表已存在，无需迁移。")
            return

        print(f"需要创建的表: {', '.join(missing)}")

        # 只创建缺失的表
        tables_to_create = [
            Base.metadata.tables[t] for t in missing if t in Base.metadata.tables
        ]

        if tables_to_create:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(
                    sync_conn, tables=tables_to_create
                )
            )
            print(f"成功创建表: {', '.join(missing)}")
        else:
            print("警告: 未在 metadata 中找到对应表定义，请确认模型已正确导入。")


if __name__ == "__main__":
    asyncio.run(migrate_add_expansion())