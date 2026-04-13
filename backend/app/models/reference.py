"""
参考小说模型
支持上传、分类、分析参考小说
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, func, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReferenceNovel(Base):
    """参考小说"""
    __tablename__ = "reference_novels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # 所属用户
    owner_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # 基本信息
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    author: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 类型：科幻/奇幻/武侠/言情/悬疑/历史/都市/恐怖/军事/其他
    source: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 来源：起点/纵横/自有

    # 分类标签
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 数组 ["标签1", "标签2"]
    reference_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 参考类型：style(文风)/structure(结构)/worldbuilding(世界观)/character(角色)/dialogue(对话)/all(综合)

    # 文件信息
    file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 文件路径
    file_format: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # txt/epub/md

    # 内容统计
    total_chars: Mapped[int] = mapped_column(Integer, default=0)  # 总字数
    chapter_count: Mapped[int] = mapped_column(Integer, default=0)  # 章节数
    avg_chapter_length: Mapped[int] = mapped_column(Integer, default=0)  # 平均章节字数

    # 分析结果
    analysis: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON: 文风分析、关键词等
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 小说摘要/简介
    writing_style: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 文风特征描述

    # 内容存储（短篇直接存库，长篇存文件）
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 章节列表（JSON 格式）
    chapters_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # [{"title":"第一章","content":"...","char_count":1000}]

    # 评分和备注
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-5 星评分
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 用户笔记

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    def __repr__(self):
        return f"<ReferenceNovel(id={self.id}, title='{self.title}', genre='{self.genre}')>"
