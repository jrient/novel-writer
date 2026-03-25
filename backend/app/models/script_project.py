"""
剧本项目模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.script_node import ScriptNode
    from app.models.script_session import ScriptSession


class ScriptProject(Base):
    """剧本项目表"""
    __tablename__ = "script_projects"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联用户
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属用户ID",
    )

    # 基本信息
    title: Mapped[str] = mapped_column(String(200), nullable=False, comment="剧本标题")

    # 剧本类型: explanatory=说明类, dynamic=动态类
    script_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="剧本类型: explanatory/dynamic"
    )

    # 创意概念
    concept: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="创意概念")

    # 状态: drafting/outlined/writing/completed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="drafting", comment="状态"
    )

    # AI 配置
    ai_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, comment="AI配置")

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
    owner: Mapped["User"] = relationship("User", back_populates="script_projects")

    nodes: Mapped[List["ScriptNode"]] = relationship(
        "ScriptNode",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ScriptNode.sort_order",
    )

    session: Mapped[Optional["ScriptSession"]] = relationship(
        "ScriptSession",
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def __repr__(self):
        return f"<ScriptProject(id={self.id}, title='{self.title}', type='{self.script_type}')>"
