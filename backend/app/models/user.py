"""
用户模型
"""
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import String, Text, Integer, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.invitation import Invitation


class User(Base):
    """用户表"""
    __tablename__ = "users"

    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 基本信息
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True, comment="邮箱")
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="密码哈希")

    # 个人资料
    nickname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="昵称")
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="头像URL")

    # 状态
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否激活")
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否管理员")

    # 第三方登录
    github_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, index=True, comment="GitHub ID")
    wechat_openid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, index=True, comment="微信OpenID")
    wechat_unionid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, unique=True, index=True, comment="微信UnionID")

    # API Key 认证
    api_key: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True, comment="API Key"
    )
    api_key_created_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="API Key 创建时间"
    )
    api_key_last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="API Key 最后使用时间"
    )

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        onupdate=func.now(), nullable=True, comment="更新时间"
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="最后登录时间"
    )

    # 关联项目
    projects: Mapped[List["Project"]] = relationship(
        "Project",
        back_populates="owner",
        cascade="all, delete-orphan",
        order_by="Project.id.desc()",
    )

    # 创建的邀请码
    created_invitations: Mapped[List["Invitation"]] = relationship(
        "Invitation",
        foreign_keys="Invitation.created_by",
        back_populates="creator",
        cascade="all, delete-orphan",
    )

    # 使用的邀请码
    used_invitation: Mapped[Optional["Invitation"]] = relationship(
        "Invitation",
        foreign_keys="Invitation.used_by",
        back_populates="used_by_user",
        uselist=False,
    )