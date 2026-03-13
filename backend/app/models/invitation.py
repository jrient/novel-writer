"""
邀请码模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Invitation(Base):
    """邀请码表"""
    __tablename__ = "invitations"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 邀请码
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True, comment="邀请码")

    # 使用状态
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否已使用")
    used_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="使用者ID"
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="使用时间")

    # 有效期
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="过期时间")

    # 创建者
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者ID"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )

    # 关联关系
    creator: Mapped["User"] = relationship(
        "User",
        foreign_keys=[created_by],
        back_populates="created_invitations",
    )
    used_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[used_by],
        back_populates="used_invitation",
    )