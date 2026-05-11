"""改编项目模型。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class AdaptationProject(Base):
    __tablename__ = "adaptation_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False, comment="原文，写入后只读")
    intent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intensity: Mapped[int] = mapped_column(Integer, nullable=False, default=2,
                                            comment="1=替换 2=润色 3=重铸")
    era_target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsing")
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(),
                                                  onupdate=func.now())

    mappings = relationship(
        "AdaptationMappingEntry", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationMappingEntry.order_index",
    )
    versions = relationship(
        "AdaptationVersion", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationVersion.version_no",
    )
