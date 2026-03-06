"""
向量存储模型
用于存储小说片段的embedding向量
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.core.database import Base


class NovelChunk(Base):
    """小说片段向量存储"""
    __tablename__ = "novel_chunks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 关联参考小说
    reference_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # 片段信息
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)  # 片段序号
    content: Mapped[str] = mapped_column(Text, nullable=False)  # 片段内容
    char_count: Mapped[int] = mapped_column(Integer, default=0)  # 字数

    # 向量 (text-embedding-3-small 维度为 1536)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    # 元数据
    chapter_title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index('ix_novel_chunks_reference_id', 'reference_id'),
    )
