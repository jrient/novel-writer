"""
小说项目模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.chapter import Chapter
    from app.models.character import Character
    from app.models.worldbuilding import WorldbuildingEntry
    from app.models.outline import OutlineNode
    from app.models.note import Note
    from app.models.event import StoryEvent, Plotline
    from app.models.user import User


class Project(Base):
    """小说项目表"""
    __tablename__ = "projects"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 所有者
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="所有者ID")

    # 基本信息
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="项目标题")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目描述")
    genre: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="小说类型")

    # 字数统计
    target_word_count: Mapped[int] = mapped_column(Integer, default=0, comment="目标字数")
    current_word_count: Mapped[int] = mapped_column(Integer, default=0, comment="当前字数")

    # 状态: draft(草稿) / in_progress(写作中) / completed(已完成)
    status: Mapped[str] = mapped_column(String(50), default="draft", comment="项目状态")

    # 大纲内容（纯文本）
    outline: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="故事大纲")

    # 地图结构（JSON格式，存储地图->部分->章节层级）
    maps: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="地图结构")

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

    # 关联角色列表
    characters: Mapped[List["Character"]] = relationship(
        "Character",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Character.id",
    )

    # 关联世界观设定
    worldbuilding_entries: Mapped[List["WorldbuildingEntry"]] = relationship(
        "WorldbuildingEntry",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="WorldbuildingEntry.sort_order",
    )

    # 关联大纲节点
    outline_nodes: Mapped[List["OutlineNode"]] = relationship(
        "OutlineNode",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="OutlineNode.sort_order",
    )

    # 关联笔记
    notes: Mapped[List["Note"]] = relationship(
        "Note",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Note.sort_order",
    )

    # 关联故事事件
    story_events: Mapped[List["StoryEvent"]] = relationship(
        "StoryEvent",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="StoryEvent.timeline_order",
    )

    # 关联剧情线
    plotlines: Mapped[List["Plotline"]] = relationship(
        "Plotline",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Plotline.sort_order",
    )

    # 关联所有者
    owner: Mapped["User"] = relationship(
        "User",
        back_populates="projects",
    )