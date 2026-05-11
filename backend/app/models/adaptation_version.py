"""改编版本（每次全场重跑产生一条）。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationVersion(Base):
    __tablename__ = "adaptation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="full_run")
    prompt_overrides: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mapping_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    project = relationship("AdaptationProject", back_populates="versions")
    scene_results = relationship(
        "AdaptationSceneResult", back_populates="version",
        cascade="all, delete-orphan", order_by="AdaptationSceneResult.scene_index",
    )
