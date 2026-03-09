"""
批量导入参考小说脚本
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.models.reference import ReferenceNovel
from app.core.config import settings


async def import_novels():
    """批量导入reference_novels目录下的小说"""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    upload_dir = "reference_novels"
    files = [f for f in os.listdir(upload_dir) if f.endswith('.txt') and not f.endswith('.tabby-upload')]

    async with async_session() as session:
        # 查询已导入的小说标题，避免重复
        from sqlalchemy import select
        existing = await session.execute(select(ReferenceNovel.title))
        existing_titles = {row[0] for row in existing.fetchall()}

        imported = 0
        skipped = 0
        for filename in files:
            file_path = os.path.join(upload_dir, filename)
            title = filename.replace('.txt', '')

            # 跳过已导入的
            if title in existing_titles:
                print(f"跳过（已存在）: {title}")
                skipped += 1
                continue

            # 读取文件内容
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # 简单分类
            genre = None
            if any(k in title for k in ['总裁', '豪门', '宠', '爱', '妻', '婚']):
                genre = '都市言情'
            elif any(k in title for k in ['修真', '仙', '神', '帝', '尊', '武']):
                genre = '玄幻修真'
            elif '快穿' in title or '重生' in title:
                genre = '快穿重生'

            # 创建记录
            novel = ReferenceNovel(
                title=title,
                genre=genre,
                file_path=file_path,
                file_format='txt',
                content=content if len(content) < 100000 else None,  # 短篇存数据库
                total_chars=len(content.replace(' ', '').replace('\n', ''))
            )
            session.add(novel)
            imported += 1
            print(f"导入: {title} ({genre})")

        await session.commit()
        print(f"\n成功导入 {imported} 本小说，跳过 {skipped} 本已存在")


if __name__ == "__main__":
    asyncio.run(import_novels())
