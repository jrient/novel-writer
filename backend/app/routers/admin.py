"""
管理后台路由 - 用户管理、系统统计
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.models.project import Project
from app.models.token_usage import TokenUsage
from app.routers.auth import get_current_superuser
from app.schemas.admin import (
    AdminUserResponse,
    AdminUserUpdate,
    AdminUserListResponse,
    AdminResetPassword,
    AdminStatsResponse,
    TokenUsageStatsResponse,
    TokenUsageListResponse,
    TokenUsageRecord,
    UserTokenSummary,
    DailyTokenUsage,
)

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["管理后台"],
    dependencies=[Depends(get_current_superuser)],
)


@router.get("/users", response_model=AdminUserListResponse, summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词（用户名/邮箱/昵称）"),
    is_active: Optional[bool] = Query(None, description="按激活状态筛选"),
    is_superuser: Optional[bool] = Query(None, description="按管理员角色筛选"),
    db: AsyncSession = Depends(get_db),
):
    """获取用户列表（分页、搜索、筛选）"""
    # 构建基础查询
    query = select(User)
    count_query = select(func.count(User.id))

    # 搜索条件
    if search:
        search_filter = or_(
            User.username.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
            User.nickname.ilike(f"%{search}%"),
        )
        query = query.where(search_filter)
        count_query = count_query.where(search_filter)

    # 筛选条件
    if is_active is not None:
        query = query.where(User.is_active == is_active)
        count_query = count_query.where(User.is_active == is_active)

    if is_superuser is not None:
        query = query.where(User.is_superuser == is_superuser)
        count_query = count_query.where(User.is_superuser == is_superuser)

    # 获取总数
    total_result = await db.execute(count_query)
    total = total_result.scalar()

    # 分页查询
    offset = (page - 1) * page_size
    query = query.order_by(User.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    users = result.scalars().all()

    # 批量查询项目数量
    user_ids = [u.id for u in users]
    if user_ids:
        project_counts_result = await db.execute(
            select(Project.owner_id, func.count(Project.id))
            .where(Project.owner_id.in_(user_ids))
            .group_by(Project.owner_id)
        )
        project_counts = dict(project_counts_result.all())

        token_counts_result = await db.execute(
            select(TokenUsage.user_id, func.coalesce(func.sum(TokenUsage.total_tokens), 0))
            .where(TokenUsage.user_id.in_(user_ids))
            .group_by(TokenUsage.user_id)
        )
        token_counts = dict(token_counts_result.all())
    else:
        project_counts = {}
        token_counts = {}

    # 构建响应
    items = []
    for user in users:
        user_data = AdminUserResponse.model_validate(user)
        user_data.project_count = project_counts.get(user.id, 0)
        user_data.total_tokens = token_counts.get(user.id, 0)
        items.append(user_data)

    return AdminUserListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse, summary="用户详情")
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """获取用户详情（含项目数量）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 查询项目数量
    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == user_id)
    )
    project_count = count_result.scalar()

    user_data = AdminUserResponse.model_validate(user)
    user_data.project_count = project_count
    return user_data


@router.put("/users/{user_id}", response_model=AdminUserResponse, summary="编辑用户")
async def update_user(
    user_id: int,
    user_data: AdminUserUpdate,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """编辑用户（昵称、邮箱、管理员状态）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 不允许修改自己的管理员状态
    if user_id == current_user.id and user_data.is_superuser is not None and not user_data.is_superuser:
        raise HTTPException(status_code=400, detail="不能取消自己的管理员权限")

    # 检查邮箱唯一性
    if user_data.email is not None and user_data.email != user.email:
        existing = await db.execute(
            select(User).where(User.email == user_data.email, User.id != user_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="邮箱已被其他用户使用")
        user.email = user_data.email

    if user_data.nickname is not None:
        user.nickname = user_data.nickname
    if user_data.is_superuser is not None:
        user.is_superuser = user_data.is_superuser

    await db.commit()
    await db.refresh(user)

    # 查询项目数量
    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == user_id)
    )
    project_count = count_result.scalar()

    response = AdminUserResponse.model_validate(user)
    response.project_count = project_count
    return response


@router.post("/users/{user_id}/toggle-active", response_model=AdminUserResponse, summary="启用/禁用用户")
async def toggle_user_active(
    user_id: int,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """启用/禁用用户"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己的账号")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.is_active = not user.is_active
    await db.commit()
    await db.refresh(user)

    count_result = await db.execute(
        select(func.count(Project.id)).where(Project.owner_id == user_id)
    )
    project_count = count_result.scalar()

    response = AdminUserResponse.model_validate(user)
    response.project_count = project_count
    return response


@router.post("/users/{user_id}/reset-password", summary="重置用户密码")
async def reset_user_password(
    user_id: int,
    password_data: AdminResetPassword,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """重置用户密码"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    return {"detail": "密码重置成功"}


@router.get("/stats", response_model=AdminStatsResponse, summary="系统统计")
async def get_stats(
    db: AsyncSession = Depends(get_db),
):
    """获取系统统计数据"""
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )).scalar()
    superuser_count = (await db.execute(
        select(func.count(User.id)).where(User.is_superuser == True)
    )).scalar()
    total_projects = (await db.execute(select(func.count(Project.id)))).scalar()
    total_tokens = (await db.execute(
        select(func.coalesce(func.sum(TokenUsage.total_tokens), 0))
    )).scalar()

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        superuser_count=superuser_count,
        total_projects=total_projects,
        total_tokens=total_tokens,
    )


@router.get("/token-usage/stats", response_model=TokenUsageStatsResponse, summary="Token 使用统计")
async def get_token_usage_stats(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: AsyncSession = Depends(get_db),
):
    """获取 Token 使用统计（按提供商、按用户汇总）"""
    from datetime import datetime, timedelta
    since = datetime.utcnow() - timedelta(days=days)

    base_filter = TokenUsage.created_at >= since

    # 总计
    totals = (await db.execute(
        select(
            func.coalesce(func.sum(TokenUsage.total_tokens), 0),
            func.coalesce(func.sum(TokenUsage.input_tokens), 0),
            func.coalesce(func.sum(TokenUsage.output_tokens), 0),
            func.count(TokenUsage.id),
        ).where(base_filter)
    )).one()

    # 按提供商汇总
    provider_result = await db.execute(
        select(
            TokenUsage.provider,
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.input_tokens).label("input_tokens"),
            func.sum(TokenUsage.output_tokens).label("output_tokens"),
            func.count(TokenUsage.id).label("call_count"),
        ).where(base_filter)
        .group_by(TokenUsage.provider)
        .order_by(func.sum(TokenUsage.total_tokens).desc())
    )
    by_provider = [
        {
            "provider": row.provider,
            "total_tokens": row.total_tokens,
            "input_tokens": row.input_tokens,
            "output_tokens": row.output_tokens,
            "call_count": row.call_count,
        }
        for row in provider_result.all()
    ]

    # 按用户汇总（Top 20）
    user_result = await db.execute(
        select(
            TokenUsage.user_id,
            User.username,
            User.nickname,
            func.sum(TokenUsage.total_tokens).label("total_tokens"),
            func.sum(TokenUsage.input_tokens).label("input_tokens"),
            func.sum(TokenUsage.output_tokens).label("output_tokens"),
            func.count(TokenUsage.id).label("call_count"),
        ).join(User, TokenUsage.user_id == User.id)
        .where(base_filter)
        .group_by(TokenUsage.user_id, User.username, User.nickname)
        .order_by(func.sum(TokenUsage.total_tokens).desc())
        .limit(20)
    )
    by_user = [
        UserTokenSummary(
            user_id=row.user_id,
            username=row.username,
            nickname=row.nickname,
            total_tokens=row.total_tokens,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            call_count=row.call_count,
        )
        for row in user_result.all()
    ]

    return TokenUsageStatsResponse(
        total_tokens=totals[0],
        total_input_tokens=totals[1],
        total_output_tokens=totals[2],
        total_calls=totals[3],
        by_provider=by_provider,
        by_user=by_user,
    )


@router.get("/token-usage/records", response_model=TokenUsageListResponse, summary="Token 使用记录")
async def list_token_usage_records(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: Optional[int] = Query(None, description="按用户筛选"),
    provider: Optional[str] = Query(None, description="按提供商筛选"),
    db: AsyncSession = Depends(get_db),
):
    """获取 Token 使用记录列表（分页）"""
    query = select(TokenUsage, User.username).join(User, TokenUsage.user_id == User.id)
    count_query = select(func.count(TokenUsage.id))

    if user_id is not None:
        query = query.where(TokenUsage.user_id == user_id)
        count_query = count_query.where(TokenUsage.user_id == user_id)
    if provider:
        query = query.where(TokenUsage.provider == provider)
        count_query = count_query.where(TokenUsage.provider == provider)

    total = (await db.execute(count_query)).scalar()

    offset = (page - 1) * page_size
    query = query.order_by(TokenUsage.id.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    rows = result.all()

    items = []
    for usage, username in rows:
        record = TokenUsageRecord.model_validate(usage)
        record.username = username
        items.append(record)

    return TokenUsageListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/token-usage/daily", response_model=list[DailyTokenUsage], summary="每日 Token 趋势")
async def get_daily_token_usage(
    days: int = Query(30, ge=1, le=365, description="统计天数"),
    db: AsyncSession = Depends(get_db),
):
    """获取每日 Token 使用趋势数据"""
    from datetime import datetime, timedelta
    from sqlalchemy import cast, Date
    since = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        select(
            cast(TokenUsage.created_at, Date).label("date"),
            func.coalesce(func.sum(TokenUsage.total_tokens), 0).label("total_tokens"),
            func.coalesce(func.sum(TokenUsage.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(TokenUsage.output_tokens), 0).label("output_tokens"),
            func.count(TokenUsage.id).label("call_count"),
        ).where(TokenUsage.created_at >= since)
        .group_by(cast(TokenUsage.created_at, Date))
        .order_by(cast(TokenUsage.created_at, Date))
    )

    return [
        DailyTokenUsage(
            date=str(row.date),
            total_tokens=row.total_tokens,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            call_count=row.call_count,
        )
        for row in result.all()
    ]
