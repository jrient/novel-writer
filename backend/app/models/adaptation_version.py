"""改编版本（每次全场重跑产生一条）。"""
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Text, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.datetime_utils import utcnow_naive


class AdaptationVersion(Base):
    __tablename__ = "adaptation_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("adaptation_projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(20), nullable=False, default="full_run")
    prompt_overrides: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    stats: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    mapping_snapshot: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Python 侧 utcnow_naive 写入：与 completed_at（路由层显式 utcnow_naive 赋值）
    # 同基准，避免 server_default=func.now() 在 PG 容器 TZ=Asia/Shanghai 下
    # 与 UTC naive 偏差 8 小时，duration 算出负值。
    created_at: Mapped[datetime] = mapped_column(default=utcnow_naive)
    completed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    project = relationship("AdaptationProject", back_populates="versions")
    scene_results = relationship(
        "AdaptationSceneResult", back_populates="version",
        cascade="all, delete-orphan", order_by="AdaptationSceneResult.scene_index",
    )
