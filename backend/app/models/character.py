"""
角色模型 - Story Bible 核心组件
支持角色类型、性格标签、关系网络、成长弧线
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, ForeignKey, JSON, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Character(Base):
    """角色卡片模型"""
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # 基本信息
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_type: Mapped[Optional[str]] = mapped_column(String(50), default="supporting")  # protagonist/antagonist/supporting/minor
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # 角色设定
    age: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # 可以是 "25岁" 或 "少年"
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    occupation: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # 职业/身份

    # 性格与特征
    personality_traits: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON 数组字符串
    appearance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 外貌描写
    background: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 背景故事

    # 关系网络 (JSON 格式存储)
    # [{"target_id": 1, "relation": "师父", "description": "授业恩师"}]
    relationships: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 成长弧线
    growth_arc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 角色发展轨迹

    # 标签 (JSON 数组)
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # ["勇敢", "善良"]

    # 备注
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, onupdate=func.now())

    # 关系
    project = relationship("Project", back_populates="characters")

    def __repr__(self):
        return f"<Character(id={self.id}, name='{self.name}', role_type='{self.role_type}')>"