"""
数据库迁移脚本 - 添加 outline 字段到 projects 表
"""
import asyncio
import sqlite3
from sqlalchemy import text
from app.core.database import engine


async def migrate_add_outline_column():
    """添加 outline 列到 projects 表（如果不存在）"""
    async with engine.begin() as conn:
        # 检查列是否存在
        if engine.url.drivername == "sqlite":
            # SQLite 方式
            result = await conn.execute(text("PRAGMA table_info(projects)"))
            columns = [row[1] for row in result.fetchall()]

            if "outline" not in columns:
                print("Adding 'outline' column to projects table...")
                await conn.execute(text("ALTER TABLE projects ADD COLUMN outline TEXT"))
                print("Migration completed successfully.")
            else:
                print("'outline' column already exists, skipping migration.")
        else:
            # PostgreSQL 方式
            result = await conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'outline'
            """))
            if not result.fetchone():
                print("Adding 'outline' column to projects table...")
                await conn.execute(text("ALTER TABLE projects ADD COLUMN outline TEXT"))
                print("Migration completed successfully.")
            else:
                print("'outline' column already exists, skipping migration.")


if __name__ == "__main__":
    asyncio.run(migrate_add_outline_column())