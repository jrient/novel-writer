"""
Token 使用记录模型
"""
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class TokenUsage(Base):
    """Token 使用记录表"""
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 关联用户
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户ID")

    # 关联项目（可选）
    project_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("projects.id"), nullable=True, comment="项目ID")

    # AI 调用信息
    provider: Mapped[str] = mapped_column(String(50), nullable=False, comment="AI提供商")
    model: Mapped[str] = mapped_column(String(100), nullable=False, comment="模型名称")
    action: Mapped[str] = mapped_column(String(50), nullable=False, comment="操作类型")

    # Token 统计
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输入token数")
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="输出token数")
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, comment="总token数")

    # 时间
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="创建时间"
    )

    # 关联
    user: Mapped["User"] = relationship("User", backref="token_usages")
