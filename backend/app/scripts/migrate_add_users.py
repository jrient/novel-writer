"""
数据库迁移脚本 - 添加用户系统和数据隔离

运行方式: python -m app.scripts.migrate_add_users
"""
import asyncio
import secrets
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, engine, Base
from app.core.security import get_password_hash
from app.models.user import User
from app.models.invitation import Invitation


async def migrate():
    """执行迁移"""
    print("开始迁移...")

    # 1. 创建新表
    print("创建 users 和 invitations 表...")
    async with engine.begin() as conn:
        # 检查 users 表是否已存在
        result = await conn.execute(
            text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'users'
            """)
        )
        if result.fetchone():
            print("users 表已存在，跳过创建")
        else:
            await conn.execute(text("""
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    hashed_password VARCHAR(255),
                    nickname VARCHAR(100),
                    avatar_url TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_superuser BOOLEAN DEFAULT FALSE,
                    github_id VARCHAR(100) UNIQUE,
                    wechat_openid VARCHAR(100) UNIQUE,
                    wechat_unionid VARCHAR(100) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP,
                    last_login_at TIMESTAMP
                )
            """))
            # 创建索引
            await conn.execute(text("CREATE INDEX ix_users_username ON users(username)"))
            await conn.execute(text("CREATE INDEX ix_users_email ON users(email)"))
            await conn.execute(text("CREATE INDEX ix_users_github_id ON users(github_id)"))
            await conn.execute(text("CREATE INDEX ix_users_wechat_openid ON users(wechat_openid)"))
            await conn.execute(text("CREATE INDEX ix_users_wechat_unionid ON users(wechat_unionid)"))
            print("users 表创建成功")

        # 检查 invitations 表
        result = await conn.execute(
            text("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'invitations'
            """)
        )
        if result.fetchone():
            print("invitations 表已存在，跳过创建")
        else:
            await conn.execute(text("""
                CREATE TABLE invitations (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(32) NOT NULL UNIQUE,
                    is_used BOOLEAN DEFAULT FALSE,
                    used_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    used_at TIMESTAMP,
                    expires_at TIMESTAMP,
                    created_by INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            # 创建索引
            await conn.execute(text("CREATE INDEX ix_invitations_code ON invitations(code)"))
            print("invitations 表创建成功")

        # 检查 projects 表是否有 owner_id 列
        result = await conn.execute(
            text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'owner_id'
            """)
        )
        if not result.fetchone():
            print("为 projects 表添加 owner_id 列...")
            await conn.execute(text("""
                ALTER TABLE projects ADD COLUMN owner_id INTEGER
            """))
            print("owner_id 列添加成功")
        else:
            print("owner_id 列已存在，跳过")

    # 2. 创建默认管理员用户
    print("创建默认管理员用户...")
    async with async_session() as db:
        # 检查是否已有用户
        result = await db.execute(text("SELECT id FROM users LIMIT 1"))
        if result.fetchone():
            print("已有用户存在，跳过创建默认用户")
            # 获取第一个用户作为默认用户
            result = await db.execute(text("SELECT id FROM users LIMIT 1"))
            default_user_id = result.fetchone()[0]
        else:
            # 创建默认管理员
            admin_user = User(
                username="admin",
                email="admin@novel-writer.local",
                hashed_password=get_password_hash("admin123"),  # 默认密码，生产环境需修改
                nickname="管理员",
                is_active=True,
                is_superuser=True,
            )
            db.add(admin_user)
            await db.flush()
            default_user_id = admin_user.id
            print(f"默认管理员创建成功 (ID: {default_user_id})")
            print("默认账号: admin / admin123")
            print("警告: 请在生产环境中修改默认密码!")

            # 创建一些邀请码
            for _ in range(5):
                code = secrets.token_urlsafe(16)[:16].upper()
                invitation = Invitation(
                    code=code,
                    created_by=default_user_id,
                )
                db.add(invitation)

            await db.commit()
            print("已创建 5 个邀请码")

        # 3. 关联现有项目到默认用户
        print("关联现有项目到默认用户...")
        result = await db.execute(
            text("SELECT id FROM projects WHERE owner_id IS NULL")
        )
        orphan_projects = result.fetchall()

        if orphan_projects:
            await db.execute(
                text(f"UPDATE projects SET owner_id = {default_user_id} WHERE owner_id IS NULL")
            )
            await db.commit()
            print(f"已将 {len(orphan_projects)} 个项目关联到默认用户")
        else:
            print("没有需要关联的项目")

    print("迁移完成!")


if __name__ == "__main__":
    asyncio.run(migrate())