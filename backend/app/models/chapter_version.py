"""
章节版本历史模型
用于保存章节的历史版本，支持内容恢复
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chapter import Chapter


class ChapterVersion(Base):
    """章节版本历史表"""
    __tablename__ = "chapter_versions"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 外键关联章节
    chapter_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, comment="所属章节ID"
    )

    # 版本号（每个章节内递增）
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="版本号")

    # 章节标题快照
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="章节标题快照")

    # 章节内容快照
    content: Mapped[str] = mapped_column(Text, default="", comment="章节内容快照")

    # 字数统计
    word_count: Mapped[int] = mapped_column(Integer, default=0, comment="字数统计")

    # 变更说明（可选，如 "AI改写润色"、"手动编辑" 等）
    change_summary: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="变更说明"
    )

    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )

    # 反向关联到章节
    chapter: Mapped["Chapter"] = relationship("Chapter", back_populates="versions")

    # 索引：按章节ID和版本号快速查询
    __table_args__ = (
        Index("ix_chapter_versions_chapter_id_version", "chapter_id", "version_number"),
    )