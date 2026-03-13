"""
笔记模型
支持伏笔、灵感和普通笔记
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, JSON, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Note(Base):
    """笔记表 - 支持伏笔、灵感和普通笔记"""
    __tablename__ = "notes"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联项目
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID"
    )

    # 笔记类型: foreshadowing(伏笔) / inspiration(灵感) / note(普通笔记) / miaoji(妙记)
    note_type: Mapped[str] = mapped_column(String(50), default="note", comment="笔记类型")

    # 笔记内容
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="标题")
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="内容")

    # 关联章节（可选）
    related_chapter_ids: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list, comment="关联章节ID列表"
    )

    # 状态: active(活跃) / resolved(已解决) / abandoned(已放弃)
    status: Mapped[str] = mapped_column(String(50), default="active", comment="状态")

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联项目
    project: Mapped["Project"] = relationship("Project", back_populates="notes")