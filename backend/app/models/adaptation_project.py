"""改编项目模型。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.datetime_utils import utcnow_naive


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
    # 统一走 Python utcnow_naive：与代码侧手写的 utcnow_naive() 同基准（UTC naive），
    # 避免与 server_default=func.now()（PG 容器 +8 时区）混用导致 duration 错乱。
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow_naive,
                                                  onupdate=utcnow_naive)

    mappings = relationship(
        "AdaptationMappingEntry", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationMappingEntry.order_index",
    )
    versions = relationship(
        "AdaptationVersion", back_populates="project",
        cascade="all, delete-orphan", order_by="AdaptationVersion.version_no",
    )
