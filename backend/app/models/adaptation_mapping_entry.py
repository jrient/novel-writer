"""改编模块的实体映射表。"""
from typing import Optional

from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationMappingEntry(Base):
    __tablename__ = "adaptation_mapping_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="person/place/prop/era_term/other"
    )
    original_text: Mapped[str] = mapped_column(String(200), nullable=False)
    replacement_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    project = relationship("AdaptationProject", back_populates="mappings")

    __table_args__ = (
        Index("ix_adaptation_mapping_proj_origin", "project_id", "original_text", unique=True),
    )
