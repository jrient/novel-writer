"""
事件与剧情线模型
支持多剧情线追踪、因果链、锚定到大纲结构
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, JSON, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project


class Plotline(Base):
    """剧情线表"""
    __tablename__ = "plotlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, comment="剧情线名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="描述")
    color: Mapped[str] = mapped_column(String(20), default="#6B7B8D", comment="标识颜色")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), comment="创建时间")
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True, comment="更新时间")

    project: Mapped["Project"] = relationship("Project", back_populates="plotlines")


class StoryEvent(Base):
    """故事事件表"""
    __tablename__ = "story_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True, comment="项目ID"
    )

    # 基本信息
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="事件标题")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="事件描述")
    event_type: Mapped[str] = mapped_column(
        String(50), default="plot_point",
        comment="事件类型: plot_point/turning_point/revelation/conflict/resolution/foreshadowing/callback"
    )
    status: Mapped[str] = mapped_column(
        String(50), default="planned",
        comment="状态: planned/written/revised/dropped"
    )

    # 锚定到大纲结构
    anchor_type: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="锚定类型: map/part/chapter/scene"
    )
    anchor_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="锚定目标ID"
    )

    # 剧情线（多对多，用 JSON 存储 ID 列表）
    plotline_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="关联剧情线ID列表")

    # 时间线
    timeline_order: Mapped[int] = mapped_column(Integer, default=0, comment="时间线顺序")
    time_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="时间标签")

    # 关联
    character_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="参与角色ID列表")
    location_map_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="发生地点地图ID")
    cause_event_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="前因事件ID列表")
    effect_event_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="后果事件ID列表")
    foreshadow_event_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="伏笔关联事件ID")

    # 元数据
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list, comment="标签")
    importance: Mapped[str] = mapped_column(String(20), default="major", comment="重要程度: critical/major/minor")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), comment="创建时间")
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=func.now(), nullable=True, comment="更新时间")

    project: Mapped["Project"] = relationship("Project", back_populates="story_events")
