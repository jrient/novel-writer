"""
章节模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.outline import OutlineNode


class Chapter(Base):
    """章节表"""
    __tablename__ = "chapters"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键关联项目
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, comment="所属项目ID"
    )

    # 章节基本信息
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="章节标题")
    content: Mapped[str] = mapped_column(Text, default="", comment="章节内容 (JSON或纯文本)")
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="章节摘要")

    # 排序与统计
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序序号")
    word_count: Mapped[int] = mapped_column(Integer, default=0, comment="字数统计")

    # 状态: draft(草稿) / writing(写作中) / completed(已完成)
    status: Mapped[str] = mapped_column(String(50), default="draft", comment="章节状态")

    # 视角人物
    pov_character: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="视角人物"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 反向关联到项目
    project: Mapped["Project"] = relationship("Project", back_populates="chapters")

    # 关联的大纲节点（一对一）
    outline_node: Mapped[Optional["OutlineNode"]] = relationship(
        "OutlineNode", back_populates="chapter", uselist=False
    )