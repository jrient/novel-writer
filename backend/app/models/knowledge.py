"""
知识库模型
存储通过搜索获取的知识条目
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeEntry(Base):
    """知识条目"""
    __tablename__ = "knowledge_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 基本信息
    keyword: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 来源信息
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), default="web_search")  # web_search/manual/api

    # 分类标签
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 科技/历史/文化/医学等
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON数组

    # 统计
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)  # 被调用次数

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<KnowledgeEntry(id={self.id}, keyword='{self.keyword}', title='{self.title}')>"
