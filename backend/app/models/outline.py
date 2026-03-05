"""
大纲树模型 - 支持全书/卷/章/场景四级结构
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OutlineNode(Base):
    """大纲节点"""
    __tablename__ = "outline_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # 节点类型
    # book: 全书大纲
    # volume: 卷
    # chapter: 章节
    # scene: 场景
    node_type: Mapped[str] = mapped_column(String(20), nullable=False, default="chapter")

    # 标题
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # 内容/描述
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 层级结构
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("outline_nodes.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)  # 0=书, 1=卷, 2=章, 3=场景

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 关联章节 (仅 chapter 类型)
    chapter_id: Mapped[Optional[int]] = mapped_column(ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True)

    # POV 角色
    pov_character_id: Mapped[Optional[int]] = mapped_column(ForeignKey("characters.id", ondelete="SET NULL"), nullable=True)

    # 状态
    status: Mapped[str] = mapped_column(String(20), default="planning")  # planning/writing/completed

    # 预估字数
    estimated_words: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 备注
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    project = relationship("Project", back_populates="outline_nodes")
    chapter = relationship("Chapter", back_populates="outline_node")
    children = relationship("OutlineNode", backref="parent", remote_side=[id])

    def __repr__(self):
        return f"<OutlineNode(id={self.id}, title='{self.title}', type='{self.node_type}')>"