"""
管理后台相关的 Pydantic Schemas
"""
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator
import re


class AdminUserCreate(BaseModel):
    """管理员创建用户模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=100, description="密码")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('无效的邮箱格式')
        return v


class AdminUserResponse(BaseModel):
    """管理员视角的用户信息"""
    id: int
    username: str
    email: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    github_id: Optional[str] = None
    wechat_openid: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    project_count: int = 0
    total_tokens: int = 0
    has_api_key: bool = False  # 是否已生成 API Key

    class Config:
        from_attributes = True


class AdminUserUpdate(BaseModel):
    """管理员编辑用户的请求体"""
    nickname: Optional[str] = Field(None, max_length=100, description="昵称")
    email: Optional[str] = Field(None, description="邮箱")
    is_superuser: Optional[bool] = Field(None, description="是否管理员")

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v is not None and not re.match(r'^[^@]+@[^@]+\.[^@]+$', v):
            raise ValueError('无效的邮箱格式')
        return v


class AdminUserListResponse(BaseModel):
    """分页列表响应"""
    items: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminResetPassword(BaseModel):
    """重置密码请求体"""
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class AdminStatsResponse(BaseModel):
    """系统统计响应"""
    total_users: int
    active_users: int
    superuser_count: int
    total_projects: int
    total_tokens: int = 0


class TokenUsageRecord(BaseModel):
    """单条 Token 使用记录"""
    id: int
    user_id: int
    username: str = ""
    project_id: Optional[int] = None
    provider: str
    model: str
    action: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    created_at: datetime

    class Config:
        from_attributes = True


class UserTokenSummary(BaseModel):
    """用户 Token 使用汇总"""
    user_id: int
    username: str
    nickname: Optional[str] = None
    total_tokens: int
    input_tokens: int
    output_tokens: int
    call_count: int


class TokenUsageStatsResponse(BaseModel):
    """Token 使用统计响应"""
    total_tokens: int
    total_input_tokens: int
    total_output_tokens: int
    total_calls: int
    by_provider: List[dict]
    by_user: List[UserTokenSummary]


class TokenUsageListResponse(BaseModel):
    """Token 使用记录列表响应"""
    items: List[TokenUsageRecord]
    total: int
    page: int
    page_size: int


class DailyTokenUsage(BaseModel):
    """每日 Token 使用"""
    date: str
    total_tokens: int
    input_tokens: int
    output_tokens: int
    call_count: int


class ApiKeyResponse(BaseModel):
    """API Key 响应模型"""
    api_key: str


class AdminProjectResponse(BaseModel):
    """管理员视角的项目信息"""
    id: int
    title: str
    description: Optional[str] = None
    genre: Optional[str] = None
    status: str
    current_word_count: int
    target_word_count: Optional[int] = None
    owner_id: Optional[int] = None
    owner_username: Optional[str] = None
    owner_nickname: Optional[str] = None
    owner_email: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AdminProjectListResponse(BaseModel):
    """管理员项目列表响应"""
    items: List[AdminProjectResponse]
    total: int
    page: int
    page_size: int
