"""风格样本库 API

设计依据：docs/superpowers/specs/2026-05-26-style-sample-library-design.md 第四节。
"""
import json
import os
import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session, get_db
from app.models.style_sample import StyleSample
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.style_sample import StyleSampleSummary
from app.services import style_sample_pipeline
from app.services.file_parser import FileParser

router = APIRouter(prefix="/api/v1/style-samples", tags=["style-samples"])

UPLOAD_DIR = "uploads/style_samples"
ALLOWED_FORMATS = {"txt", "md", "markdown", "docx"}


def _parse_upload(file: UploadFile, raw: bytes) -> str:
    fmt = (os.path.splitext(file.filename or "")[1] or "").lstrip(".").lower()
    if fmt not in ALLOWED_FORMATS:
        raise HTTPException(400, f"不支持的文件格式 .{fmt}（仅 txt/md/docx）")
    parser = FileParser()
    try:
        if fmt == "docx":
            result = parser.parse_docx(raw)
        elif fmt in ("md", "markdown"):
            result = parser.parse_markdown(raw)
        else:
            result = parser.parse_txt(raw)
    except Exception as e:
        raise HTTPException(400, f"文件解析失败: {e}")
    return result.content if hasattr(result, "content") else str(result)


def _to_summary(s: StyleSample) -> dict:
    return {
        "id": s.id,
        "title": s.title,
        "author": s.author,
        "source": s.source,
        "genre": s.genre,
        "tags": s.tags,
        "total_chars": s.total_chars,
        "index_status": s.index_status,
        "index_error": s.index_error,
        "extracted_at": s.extracted_at.isoformat() if s.extracted_at else None,
        "created_at": s.created_at.isoformat(),
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


@router.post("", response_model=StyleSampleSummary)
async def upload_sample(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    author: Optional[str] = Form(default=None),
    source: Optional[str] = Form(default=None),
    genre: Optional[str] = Form(default=None),
    tags: Optional[str] = Form(default=None),
    notes: Optional[str] = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await file.read()
    content = _parse_upload(file, raw)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    fmt = (os.path.splitext(file.filename or "")[1] or ".txt").lstrip(".").lower()
    fname = f"{uuid.uuid4().hex}.{fmt}"
    fpath = os.path.join(UPLOAD_DIR, fname)
    with open(fpath, "wb") as f:
        f.write(raw)

    sample = StyleSample(
        title=title,
        author=author,
        source=source,
        genre=genre,
        tags=tags,
        notes=notes,
        file_path=fpath,
        file_format=fmt,
        content=content,
        total_chars=len(content),
        index_status="pending",
    )
    db.add(sample)
    await db.commit()
    await db.refresh(sample)

    background.add_task(style_sample_pipeline.run, async_session, sample.id)
    return _to_summary(sample)
