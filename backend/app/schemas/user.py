"""
用户相关的 Pydantic Schemas
"""
from datetime import datetime
from typing import Optional
import re

from pydantic import BaseModel, Field, field_validator


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        # 简单的邮箱格式验证
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('无效的邮箱格式')
        return v


class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    invitation_code: str = Field(..., description="邀请码")


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str = Field(..., description="用户名或邮箱")
    password: str = Field(..., description="密码")


class UserUpdate(BaseModel):
    """用户更新模型"""
    nickname: Optional[str] = Field(None, max_length=100, description="昵称")
    avatar_url: Optional[str] = Field(None, description="头像URL")


class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Token(BaseModel):
    """令牌响应模型"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    """令牌载荷模型"""
    sub: int
    exp: datetime
    type: str


class PasswordChange(BaseModel):
    """密码修改模型"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class InvitationCreate(BaseModel):
    """邀请码创建模型"""
    count: int = Field(1, ge=1, le=100, description="生成数量")
    expires_days: Optional[int] = Field(None, ge=1, le=365, description="有效天数")


class InvitationResponse(BaseModel):
    """邀请码响应模型"""
    id: int
    code: str
    is_used: bool
    used_by: Optional[int] = None
    used_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_by: int
    created_at: datetime

    class Config:
        from_attributes = True


class OAuthAuthorize(BaseModel):
    """OAuth 授权响应"""
    authorize_url: str


class OAuthCallback(BaseModel):
    """OAuth 回调响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse