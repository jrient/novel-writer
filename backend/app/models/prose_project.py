"""散文改写项目 ORM 模型。"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.datetime_utils import utcnow_naive

if TYPE_CHECKING:
    from app.models.user import User


class ProseProject(Base):
    __tablename__ = "prose_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    script_project_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    script_project_title: Mapped[Optional[str]] = mapped_column(String(200))
    script_content: Mapped[Optional[str]] = mapped_column(Text)
    outline: Mapped[Optional[str]] = mapped_column(Text)  # 内部大纲，不对外暴露
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    genre: Mapped[Optional[str]] = mapped_column(String(50))
    style_snapshot: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    total_scenes: Mapped[int] = mapped_column(Integer, default=0)
    done_scenes: Mapped[int] = mapped_column(Integer, default=0)
    failed_scenes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=utcnow_naive)

    scenes: Mapped[List["ProseScene"]] = relationship(
        "ProseScene",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProseScene.scene_index",
    )


class ProseScene(Base):
    __tablename__ = "prose_scenes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("prose_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scene_index: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_title: Mapped[str] = mapped_column(String(200), default="")
    original_scene_text: Mapped[str] = mapped_column(Text, nullable=False)
    prose_text: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error: Mapped[Optional[str]] = mapped_column(Text)
    token_used: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=utcnow_naive)

    project: Mapped["ProseProject"] = relationship("ProseProject", back_populates="scenes")
