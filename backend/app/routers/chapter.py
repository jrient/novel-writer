"""
章节路由
处理章节的 CRUD 操作及排序
"""
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.chapter import Chapter
from app.models.project import Project
from app.schemas.chapter import ChapterCreate, ChapterUpdate, ChapterResponse, ChapterBatchDeleteRequest, ChapterReorderItem, ChapterReorderRequest

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


async def _get_project_or_404(project_id: int, db: AsyncSession) -> Project:
    """获取项目，不存在则抛出 404"""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@router.get("/", response_model=List[ChapterResponse])
async def list_chapters(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    """列出项目所有章节，按 sort_order 升序排列"""
    await _get_project_or_404(project_id, db)
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
    db: AsyncSession = Depends(get_db),
):
    """创建新章节，未指定 sort_order 时自动追加到末尾"""
    await _get_project_or_404(project_id, db)

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
    project = await _get_project_or_404(project_id, db)
    project.current_word_count += word_count

    await db.commit()
    await db.refresh(chapter)
    return chapter


@router.post("/batch-delete", status_code=204)
async def batch_delete_chapters(
    project_id: int,
    payload: ChapterBatchDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量删除章节，同步减少项目字数"""
    if not payload.ids:
        return

    project = await _get_project_or_404(project_id, db)

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


@router.get("/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    project_id: int,
    chapter_id: int,
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
    db: AsyncSession = Depends(get_db),
):
    """
    更新章节信息
    若 content 有变化，自动重新计算 word_count 并同步项目总字数
    """
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
        old_word_count = chapter.word_count
        new_word_count = _calculate_word_count(update_data["content"])
        update_data["word_count"] = new_word_count

        # 更新项目总字数
        project = await _get_project_or_404(project_id, db)
        project.current_word_count = max(
            0, project.current_word_count - old_word_count + new_word_count
        )

    for key, value in update_data.items():
        setattr(chapter, key, value)

    await db.commit()
    await db.refresh(chapter)
    return chapter


@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    project_id: int,
    chapter_id: int,
    db: AsyncSession = Depends(get_db),
):
    """删除章节，同步减少项目字数"""
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
    project = await _get_project_or_404(project_id, db)
    project.current_word_count = max(0, project.current_word_count - chapter.word_count)

    await db.delete(chapter)
    await db.commit()


@router.post("/reorder", response_model=List[ChapterResponse])
async def reorder_chapters(
    project_id: int,
    payload: ChapterReorderRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量更新章节排序
    请求体为 {orders: [{id: int, sort_order: int}, ...]}
    """
    await _get_project_or_404(project_id, db)
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
