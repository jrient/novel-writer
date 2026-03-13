"""
导出路由
支持导出项目为 TXT 或 Markdown 格式
"""
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_project_with_auth
from app.models.project import Project
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/export",
    tags=["export"],
)


@router.get("/txt")
async def export_txt(
    project_id: int,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """导出项目为纯文本格式"""
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.sort_order)
    )
    chapters = chapters_result.scalars().all()

    lines = [project.title, "=" * len(project.title) * 2, ""]
    if project.description:
        lines.extend([project.description, ""])

    for ch in chapters:
        lines.append(f"\n{'=' * 40}")
        lines.append(f"  {ch.title}")
        lines.append(f"{'=' * 40}\n")
        if ch.content:
            lines.append(ch.content)
        lines.append("")

    lines.append(f"\n--- 共 {project.current_word_count} 字 | 导出于 {datetime.now().strftime('%Y-%m-%d %H:%M')} ---")

    content = "\n".join(lines)
    filename = quote(f"{project.title}.txt")

    return PlainTextResponse(
        content=content,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )


@router.get("/markdown")
async def export_markdown(
    project_id: int,
    include_characters: bool = False,
    project: Project = Depends(get_project_with_auth),
    db: AsyncSession = Depends(get_db),
):
    """导出项目为 Markdown 格式"""
    chapters_result = await db.execute(
        select(Chapter)
        .where(Chapter.project_id == project_id)
        .order_by(Chapter.sort_order)
    )
    chapters = chapters_result.scalars().all()

    lines = [f"# {project.title}", ""]
    if project.genre:
        lines.append(f"> 类型：{project.genre}")
    if project.description:
        lines.append(f"> {project.description}")
    lines.append("")
    lines.append(f"**总字数：{project.current_word_count:,}**")
    lines.append("")
    lines.append("---")
    lines.append("")

    # 目录
    if chapters:
        lines.append("## 目录\n")
        for i, ch in enumerate(chapters, 1):
            lines.append(f"{i}. [{ch.title}](#{ch.title}) ({ch.word_count:,} 字)")
        lines.append("")
        lines.append("---")
        lines.append("")

    # 章节内容
    for ch in chapters:
        lines.append(f"## {ch.title}\n")
        if ch.content:
            # 将纯文本转为段落
            paragraphs = ch.content.split("\n")
            for p in paragraphs:
                p = p.strip()
                if p:
                    lines.append(p)
                    lines.append("")
        lines.append("---")
        lines.append("")

    # 角色列表（可选）
    if include_characters:
        chars_result = await db.execute(
            select(Character).where(Character.project_id == project_id)
        )
        characters = chars_result.scalars().all()
        if characters:
            lines.append("## 角色设定\n")
            for char in characters:
                lines.append(f"### {char.name}")
                if char.role_type:
                    role_map = {
                        "protagonist": "主角",
                        "antagonist": "反派",
                        "supporting": "配角",
                        "minor": "龙套",
                    }
                    lines.append(f"- **类型**：{role_map.get(char.role_type, char.role_type)}")
                if char.personality_traits:
                    lines.append(f"- **性格**：{char.personality_traits}")
                if char.appearance:
                    lines.append(f"- **外貌**：{char.appearance}")
                if char.background:
                    lines.append(f"- **背景**：{char.background}")
                lines.append("")

    content = "\n".join(lines)
    filename = quote(f"{project.title}.md")

    return PlainTextResponse(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{filename}",
        },
    )