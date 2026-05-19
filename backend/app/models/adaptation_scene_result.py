"""改编单场结果。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.datetime_utils import utcnow_naive


class AdaptationSceneResult(Base):
    __tablename__ = "adaptation_scene_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_versions.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    original_scene_text: Mapped[str] = mapped_column(Text, nullable=False)
    rewritten_scene_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scene_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    token_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_count_delta_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    manual_edits: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    # 走 Python utcnow_naive，与 version/project 同基准（UTC naive）
    updated_at: Mapped[datetime] = mapped_column(
        default=utcnow_naive, onupdate=utcnow_naive
    )

    version = relationship("AdaptationVersion", back_populates="scene_results")

    __table_args__ = (
        UniqueConstraint("version_id", "scene_index", name="uq_adaptation_version_scene"),
    )
