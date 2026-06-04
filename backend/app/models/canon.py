"""原作设定 canon 模型：挂在 ReferenceNovel 上，跨项目复用。
- CanonEntity: 多态设定条目（角色/地点/能力/势力/世界观规则/事件）
- CanonExtractionJob: 提取任务，状态机 + 进度计数（仿 ProseProject）
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, Float, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.datetime_utils import utcnow_naive


class CanonEntity(Base):
    """原作设定条目（多态）"""
    __tablename__ = "canon_entities"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("reference_novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # character / location / ability / faction / worldrule / event
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    aliases: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    # 溯源：[{"chapter": <分块标签，如 "片段3">, "quote": "<≤40字原文>"}]
    source_refs: Mapped[Optional[list]] = mapped_column(JSON, default=list)
    importance: Mapped[str] = mapped_column(String(20), default="major")  # critical/major/minor
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    # ai_extracted / user_verified / user_edited / user_added
    review_status: Mapped[str] = mapped_column(String(20), default="ai_extracted")

    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=utcnow_naive)

    def __repr__(self):
        return f"<CanonEntity(id={self.id}, type='{self.entity_type}', name='{self.canonical_name}')>"


class CanonExtractionJob(Base):
    """设定提取任务"""
    __tablename__ = "canon_extraction_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reference_id: Mapped[int] = mapped_column(
        ForeignKey("reference_novels.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/processing/done/failed
    model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    chunk_total: Mapped[int] = mapped_column(Integer, default=0)
    chunk_done: Mapped[int] = mapped_column(Integer, default=0)
    failed_chunks: Mapped[int] = mapped_column(Integer, default=0)
    entity_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=utcnow_naive)

    def __repr__(self):
        return f"<CanonExtractionJob(id={self.id}, ref={self.reference_id}, status='{self.status}')>"
