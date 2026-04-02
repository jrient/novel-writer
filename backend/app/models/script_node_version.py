"""
剧本节点版本历史模型
保存 episode 节点的历史版本，支持内容恢复
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Text, Integer, ForeignKey, func, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.script_node import ScriptNode


class ScriptNodeVersion(Base):
    """剧本节点版本历史表"""
    __tablename__ = "script_node_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("script_nodes.id", ondelete="CASCADE"),
        nullable=False, comment="所属节点ID"
    )

    version_number: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="版本号（节点内递增）"
    )

    title: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="标题快照"
    )

    content: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="内容快照"
    )

    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual",
        comment="来源: init/ai_apply/switch/manual"
    )

    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )

    node: Mapped["ScriptNode"] = relationship("ScriptNode", back_populates="versions")

    __table_args__ = (
        Index("ix_snv_node_version", "node_id", "version_number"),
    )
