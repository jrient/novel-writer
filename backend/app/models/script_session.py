"""
剧本会话模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Integer, JSON, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.script_project import ScriptProject
    from app.models.script_node import ScriptNode


class ScriptSession(Base):
    """剧本AI会话表"""
    __tablename__ = "script_sessions"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联项目 (唯一，一对一)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("script_projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        comment="所属剧本项目ID",
    )

    # 状态: init/collecting/generating/done
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="init", comment="会话状态"
    )

    # 对话历史
    history: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list, comment="对话历史"
    )

    # 大纲草稿
    outline_draft: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="大纲草稿"
    )

    # 当前处理的节点
    current_node_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("script_nodes.id", ondelete="SET NULL"),
        nullable=True,
        comment="当前处理节点ID",
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )

    # 关联关系
    project: Mapped["ScriptProject"] = relationship(
        "ScriptProject", back_populates="session"
    )

    def __repr__(self):
        return f"<ScriptSession(id={self.id}, project_id={self.project_id}, state='{self.state}')>"
