"""
世界观设定模型 - 支持分类、触发关键词、层级结构
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WorldbuildingEntry(Base):
    """世界观设定条目"""
    __tablename__ = "worldbuilding_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # 分类 (地理/历史/势力/魔法体系/社会制度/文化习俗等)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="其他")

    # 标题
    title: Mapped[str] = mapped_column(String(200), nullable=False)

    # 内容
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 触发关键词 (JSON 数组字符串)
    # 编辑器中输入这些词时自动提示此设定
    trigger_keywords: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # ["灵石", "修炼"]

    # 层级结构
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("worldbuilding_entries.id"), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)  # 0=顶层, 1=二级, ...

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # 图标/颜色标识
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    project = relationship("Project", back_populates="worldbuilding_entries")
    children = relationship("WorldbuildingEntry", backref="parent", remote_side=[id])

    def __repr__(self):
        return f"<WorldbuildingEntry(id={self.id}, title='{self.title}', category='{self.category}')>"