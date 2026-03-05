"""
小说项目模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chapter import Chapter


class Project(Base):
    """小说项目表"""
    __tablename__ = "projects"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目标题")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目描述")
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="小说类型")

    # 字数统计
    target_word_count: Mapped[int] = mapped_column(Integer, default=0, comment="目标字数")
    current_word_count: Mapped[int] = mapped_column(Integer, default=0, comment="当前字数")

    # 状态: draft(草稿) / in_progress(写作中) / completed(已完成)
    status: Mapped[str] = mapped_column(String(50), default="draft", comment="项目状态")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联章节列表
    chapters: Mapped[List["Chapter"]] = relationship(
        "Chapter",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Chapter.sort_order",
    )
