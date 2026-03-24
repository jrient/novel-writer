"""
章节路由
处理章节的 CRUD 操作及排序
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.chapter import (
    ChapterCreate, ChapterUpdate, ChapterResponse,
    ChapterBatchDeleteRequest, ChapterReorderItem, ChapterReorderRequest,
    ChapterVersionResponse, ChapterVersionDetail, ChapterVersionRestore
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/chapters",
    tags=["chapters"],
)


def _calculate_word_count(content: str) -> int:
    """
    近似计算中文字数
    去除空格和换行后统计字符数
    """
    return len(content.replace(" ", "").replace("\n", ""))


@router.get("/", response_model=List[ChapterResponse])
async def list_chapters(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """列出项目所有章节，按 sort_order 升序排列"""
    stmt = (
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.sort_order)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/", response_model=ChapterResponse, status_code=201)
async def create_chapter(
    project_id: int,
    payload: ChapterCreate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """创建新章节，未指定 sort_order 时自动追加到末尾"""
    try:
        # 若未指定排序，取当前最大值 + 1
        if payload.sort_order is None:
            max_result = await db.execute(
                select(func.max(Chapter.sort_order)).where(Chapter.project_id == project_id)
            )
            max_order = max_result.scalar() or -1
            sort_order = max_order + 1
        else:
            sort_order = payload.sort_order

        # 计算初始字数
        word_count = _calculate_word_count(payload.content)

        chapter_data = payload.model_dump(exclude={"sort_order"})
        chapter = Chapter(
            **chapter_data,
            project_id=project_id,
            sort_order=sort_order,
            word_count=word_count,
        )
        db.add(chapter)

        # 同步更新项目字数
        project.current_word_count += word_count

        await db.commit()
        await db.refresh(chapter)
        return chapter
    except Exception as e:
        await db.rollback()
        logger.error(f"创建章节失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="创建章节失败")


@router.post("/batch-delete", status_code=204)
async def batch_delete_chapters(
    project_id: int,
    payload: ChapterBatchDeleteRequest,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """批量删除章节，同步减少项目字数"""
    if not payload.ids:
        return

    try:
        # 批量获取所有目标章节
        stmt = select(Chapter).where(
            Chapter.id.in_(payload.ids),
            Chapter.project_id == project_id,
        )
        result = await db.execute(stmt)
        chapters_to_delete = result.scalars().all()

        if not chapters_to_delete:
            raise HTTPException(status_code=404, detail="未找到要删除的章节")

        # 计算总字数并同步项目字数
        total_word_count = sum(c.word_count for c in chapters_to_delete)
        project.current_word_count = max(0, project.current_word_count - total_word_count)

        # 批量删除
        for chapter in chapters_to_delete:
            await db.delete(chapter)

        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"批量删除章节失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="批量删除章节失败")


@router.get("/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    project_id: int,
    chapter_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取章节详情"""
    result = await db.execute(
        select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == project_id,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")
    return chapter


@router.put("/{chapter_id}", response_model=ChapterResponse)
async def update_chapter(
    project_id: int,
    chapter_id: int,
    payload: ChapterUpdate,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    更新章节信息
    若 content 有变化，自动重新计算 word_count 并同步项目总字数
    内容变化超过 100 字符时自动保存版本快照
    """
    try:
        result = await db.execute(
            select(Chapter).where(
                Chapter.id == chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise HTTPException(status_code=404, detail="章节不存在")

        update_data = payload.model_dump(exclude_unset=True)

        # 若更新了 content，重新计算字数并同步项目字数
        if "content" in update_data:
            old_content = chapter.content or ""
            new_content = update_data["content"] or ""

            # 内容变化超过 30 字符时保存版本快照
            if abs(len(new_content) - len(old_content)) > 30:
                await _save_chapter_version(chapter, db, change_summary="内容编辑")

            old_word_count = chapter.word_count
            new_word_count = _calculate_word_count(update_data["content"])
            update_data["word_count"] = new_word_count

            # 更新项目总字数
            project.current_word_count = max(
                0, project.current_word_count - old_word_count + new_word_count
            )

        for key, value in update_data.items():
            setattr(chapter, key, value)

        await db.commit()
        await db.refresh(chapter)
        return chapter
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新章节失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="更新章节失败")


@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    project_id: int,
    chapter_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """删除章节，同步减少项目字数"""
    try:
        result = await db.execute(
            select(Chapter).where(
                Chapter.id == chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise HTTPException(status_code=404, detail="章节不存在")

        # 同步减少项目字数
        project.current_word_count = max(0, project.current_word_count - chapter.word_count)

        await db.delete(chapter)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除章节失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="删除章节失败")


@router.post("/reorder", response_model=List[ChapterResponse])
async def reorder_chapters(
    project_id: int,
    payload: ChapterReorderRequest,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """
    批量更新章节排序
    请求体为 {orders: [{id: int, sort_order: int}, ...]}
    """
    items = payload.orders

    # 批量获取所有目标章节
    chapter_ids = [item.id for item in items]
    stmt = select(Chapter).where(
        Chapter.id.in_(chapter_ids),
        Chapter.project_id == project_id,
    )
    result = await db.execute(stmt)
    chapters = {c.id: c for c in result.scalars().all()}

    # 校验所有 id 都属于该项目
    missing = set(chapter_ids) - set(chapters.keys())
    if missing:
        raise HTTPException(status_code=404, detail=f"章节不存在: {missing}")

    # 应用新排序
    for item in items:
        chapters[item.id].sort_order = item.sort_order

    await db.commit()

    # 按新排序返回
    updated = sorted(chapters.values(), key=lambda c: c.sort_order)
    for c in updated:
        await db.refresh(c)
    return updated


# ========== 版本历史相关 ==========

MAX_VERSIONS_PER_CHAPTER = 20  # 每个章节最多保留的版本数


async def _save_chapter_version(
    chapter: Chapter,
    db: AsyncSession,
    change_summary: str = None,
) -> None:
    """
    保存章节版本快照
    在更新章节内容前调用
    """
    # 不保存字数为0的内容
    if not chapter.content or chapter.word_count == 0:
        return

    # 获取当前最大版本号
    result = await db.execute(
        select(func.max(ChapterVersion.version_number)).where(
            ChapterVersion.chapter_id == chapter.id
        )
    )
    max_version = result.scalar() or 0

    # 创建新版本
    new_version = ChapterVersion(
        chapter_id=chapter.id,
        version_number=max_version + 1,
        title=chapter.title,
        content=chapter.content,
        word_count=chapter.word_count,
        change_summary=change_summary,
    )
    db.add(new_version)

    # 检查并删除超出限制的旧版本
    result = await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter.id)
        .order_by(ChapterVersion.version_number)
    )
    all_versions = result.scalars().all()

    if len(all_versions) > MAX_VERSIONS_PER_CHAPTER:
        # 删除最旧的版本
        versions_to_delete = all_versions[:len(all_versions) - MAX_VERSIONS_PER_CHAPTER]
        for v in versions_to_delete:
            await db.delete(v)


@router.get("/{chapter_id}/versions", response_model=List[ChapterVersionResponse])
async def list_chapter_versions(
    project_id: int,
    chapter_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取章节版本历史列表"""
    # 验证章节存在
    result = await db.execute(
        select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == project_id,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    # 获取版本列表，按版本号降序
    result = await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter_id)
        .order_by(desc(ChapterVersion.version_number))
    )
    versions = result.scalars().all()
    return versions


@router.get("/{chapter_id}/versions/{version_id}", response_model=ChapterVersionDetail)
async def get_chapter_version(
    project_id: int,
    chapter_id: int,
    version_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """获取章节版本详情"""
    # 验证章节存在
    result = await db.execute(
        select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == project_id,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    # 获取版本
    result = await db.execute(
        select(ChapterVersion).where(
            ChapterVersion.id == version_id,
            ChapterVersion.chapter_id == chapter_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise HTTPException(status_code=404, detail="版本不存在")

    return version


@router.post("/{chapter_id}/versions/save", response_model=ChapterVersionResponse)
async def save_chapter_version(
    project_id: int,
    chapter_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """手动保存章节版本快照"""
    result = await db.execute(
        select(Chapter).where(
            Chapter.id == chapter_id,
            Chapter.project_id == project_id,
        )
    )
    chapter = result.scalar_one_or_none()
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    if not chapter.content:
        raise HTTPException(status_code=400, detail="章节内容为空，无法保存版本")

    await _save_chapter_version(chapter, db, change_summary="手动保存")
    await db.commit()

    # 返回刚保存的版本
    result = await db.execute(
        select(ChapterVersion)
        .where(ChapterVersion.chapter_id == chapter_id)
        .order_by(desc(ChapterVersion.version_number))
        .limit(1)
    )
    version = result.scalar_one()
    return version


@router.post("/{chapter_id}/versions/{version_id}/restore", response_model=ChapterVersionRestore)
async def restore_chapter_version(
    project_id: int,
    chapter_id: int,
    version_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """恢复到指定版本"""
    try:
        # 获取章节
        result = await db.execute(
            select(Chapter).where(
                Chapter.id == chapter_id,
                Chapter.project_id == project_id,
            )
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            raise HTTPException(status_code=404, detail="章节不存在")

        # 获取版本
        result = await db.execute(
            select(ChapterVersion).where(
                ChapterVersion.id == version_id,
                ChapterVersion.chapter_id == chapter_id,
            )
        )
        version = result.scalar_one_or_none()
        if not version:
            raise HTTPException(status_code=404, detail="版本不存在")

        # 保存当前版本快照
        await _save_chapter_version(chapter, db, change_summary="恢复版本前的自动备份")

        # 计算字数变化并更新项目字数
        old_word_count = chapter.word_count
        new_word_count = version.word_count

        project.current_word_count = max(
            0, project.current_word_count - old_word_count + new_word_count
        )

        # 恢复章节内容
        chapter.title = version.title
        chapter.content = version.content
        chapter.word_count = version.word_count

        await db.commit()
        await db.refresh(chapter)

        return ChapterVersionRestore(
            message=f"已恢复到版本 #{version.version_number}",
            chapter=chapter,
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"恢复章节版本失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="恢复章节版本失败")