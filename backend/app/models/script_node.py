"""
剧本节点模型
"""
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Text, Integer, Boolean, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ScriptNode(Base):
    """剧本节点表"""
    __tablename__ = "script_nodes"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联项目
    project_id: Mapped[int] = mapped_column(
        ForeignKey("script_projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属剧本项目ID",
    )

    # 父节点 (自引用)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("script_nodes.id", ondelete="CASCADE"),
        nullable=True,
        comment="父节点ID",
    )

    # 节点类型: episode/scene/dialogue/action/effect/inner_voice/section/narration/intro
    node_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="节点类型"
    )

    # 标题
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="标题")

    # 内容
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="内容")

    # 说话者
    speaker: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="说话者")

    # 视觉描述
    visual_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="视觉描述")

    # 排序
    sort_order: Mapped[int] = mapped_column(Integer, default=0, comment="排序")

    # 是否完成
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否完成")

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
    project = relationship("ScriptProject", back_populates="nodes")

    children: Mapped[List["ScriptNode"]] = relationship(
        "ScriptNode",
        cascade="all, delete-orphan",
        back_populates="parent",
        order_by="ScriptNode.sort_order",
    )

    parent: Mapped[Optional["ScriptNode"]] = relationship(
        "ScriptNode",
        back_populates="children",
        remote_side="ScriptNode.id",
    )

    def __repr__(self):
        return f"<ScriptNode(id={self.id}, type='{self.node_type}', title='{self.title}')>"
