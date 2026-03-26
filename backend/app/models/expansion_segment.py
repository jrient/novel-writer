"""
扩写片段模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.expansion_project import ExpansionProject


class ExpansionSegment(Base):
    """扩写片段表"""
    __tablename__ = "expansion_segments"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联项目
    project_id: Mapped[int] = mapped_column(
        ForeignKey("expansion_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属扩写项目ID",
    )

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    # 标题
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="标题")

    # 原始内容
    original_content: Mapped[str] = mapped_column(Text, nullable=False, comment="原始内容")

    # 扩写内容
    expanded_content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="扩写内容"
    )

    # 扩写深度覆盖（可覆盖项目设置）
    expansion_level: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="覆盖扩写深度: light/medium/deep"
    )

    # 自定义指令（片段级覆盖）
    custom_instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="自定义指令"
    )

    # 状态: pending/expanding/completed/error/skipped
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", comment="状态: pending/expanding/completed/error/skipped"
    )

    # 错误信息
    error_message: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="错误信息"
    )

    # 原始字数
    original_word_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="原始字数"
    )

    # 扩写字数
    expanded_word_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="扩写字数"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联关系
    project: Mapped["ExpansionProject"] = relationship(
        "ExpansionProject", back_populates="segments"
    )

    def __repr__(self):
        return f"<ExpansionSegment(id={self.id}, sort_order={self.sort_order}, status='{self.status}')>"