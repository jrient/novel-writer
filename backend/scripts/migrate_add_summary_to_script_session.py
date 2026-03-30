"""
数据库迁移脚本 - 为 script_sessions 表添加 summary 字段

Revision ID: add_summary_to_script_session
Revises:
Create Date: 2026-03-30

"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine


async def column_exists(conn, table_name: str, column_name: str) -> bool:
    """检查列是否存在（兼容 SQLite 和 PostgreSQL）"""
    if engine.url.drivername.startswith("sqlite"):
        result = await conn.execute(
            text(f"PRAGMA table_info({table_name})"),
        )
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns
    else:
        # PostgreSQL
        result = await conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :table_name AND column_name = :column_name"
            ),
            {"table_name": table_name, "column_name": column_name},
        )
        return result.fetchone() is not None


async def migrate_add_summary_to_script_session():
    """为 script_sessions 表添加 summary 字段"""
    async with engine.begin() as conn:
        # 检查字段是否已存在
        if await column_exists(conn, "script_sessions", "summary"):
            print("字段 'summary' 已存在于 'script_sessions' 表中，跳过迁移。")
            return

        # 添加字段
        await conn.execute(
            text("ALTER TABLE script_sessions ADD COLUMN summary JSON")
        )
        print("成功为 'script_sessions' 表添加 'summary' 字段。")


if __name__ == "__main__":
    asyncio.run(migrate_add_summary_to_script_session())