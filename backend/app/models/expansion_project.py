"""
扩写项目模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.expansion_segment import ExpansionSegment


class ExpansionProject(Base):
    """扩写项目表"""
    __tablename__ = "expansion_projects"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户ID",
    )

    # 基本信息
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="标题")

    # 来源类型: text/file/chapter
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="来源类型: text/file/chapter"
    )

    # 来源引用（如果是chapter类型，存储chapter_id等）
    source_ref: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="来源引用"
    )

    # 原始文本
    original_text: Mapped[str] = mapped_column(Text, nullable=False, comment="原始文本")

    # 原文字数
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, comment="原文字数")

    # 摘要/概要（AI分析结果）
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="摘要")

    # 风格画像（AI分析结果）
    style_profile: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="风格画像"
    )

    # 扩写倍数 (1.5, 2.0, 2.5, 3.0 等)
    expansion_level: Mapped[float] = mapped_column(
        nullable=False, default=2.0, comment="扩写倍数"
    )

    # 目标字数
    target_word_count: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="目标字数"
    )

    # 风格指导
    style_instructions: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="风格指导"
    )

    # AI配置
    ai_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="AI配置")

    # 状态: created/analyzing/segmenting/expanding/completed/failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created", comment="状态"
    )

    # 执行模式: auto/manual
    execution_mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="auto", comment="执行模式"
    )

    # 版本号（乐观锁）
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, comment="版本号"
    )

    # 元数据 (column name "metadata" but attribute name metadata_)
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSON, nullable=True, comment="元数据"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联关系
    owner: Mapped["User"] = relationship("User", back_populates="expansion_projects")

    segments: Mapped[List["ExpansionSegment"]] = relationship(
        "ExpansionSegment",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ExpansionSegment.sort_order",
    )

    def __repr__(self):
        return f"<ExpansionProject(id={self.id}, title='{self.title}', status='{self.status}')>"