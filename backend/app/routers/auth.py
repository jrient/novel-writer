"""
认证路由 - 登录、注册、OAuth、邀请码管理
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    verify_token,
)
from app.models.user import User
from app.models.invitation import Invitation
from app.schemas.user import (
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
    Token,
    PasswordChange,
    InvitationCreate,
    InvitationResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])

# OAuth2 密码模式
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User:
    """获取当前登录用户（支持 JWT Token 或 API Key）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 优先 JWT Token
    if token:
        user_id = verify_token(token)
        if user_id:
            result = await db.execute(
                select(User).where(User.id == user_id, User.deleted_at == None)
            )
            user = result.scalar_one_or_none()
            if user and user.is_active:
                return user

    # 其次 API Key
    if x_api_key:
        result = await db.execute(
            select(User).where(User.api_key == x_api_key, User.deleted_at == None)
        )
        user = result.scalar_one_or_none()
        if user and user.is_active:
            # 节流更新最后使用时间（避免高并发下的频繁写库）
            if not user.api_key_last_used_at or \
               (datetime.utcnow() - user.api_key_last_used_at).total_seconds() > 300:
                user.api_key_last_used_at = datetime.utcnow()
                await db.commit()
            return user

    raise credentials_exception


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前活跃用户"""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """获取当前超级管理员用户"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return current_user


# ==================== 登录/注册 ====================

@router.post("/register", response_model=Token, summary="用户注册")
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    """用户注册（需要邀请码）"""
    # 验证邀请码
    result = await db.execute(
        select(Invitation).where(Invitation.code == user_data.invitation_code)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=400, detail="邀请码无效")

    if invitation.is_used:
        raise HTTPException(status_code=400, detail="邀请码已被使用")

    if invitation.expires_at and invitation.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="邀请码已过期")

    # 检查用户名和邮箱是否已存在
    result = await db.execute(
        select(User).where(
            or_(User.username == user_data.username, User.email == user_data.email),
            User.deleted_at == None,
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名或邮箱已被注册")

    # 创建用户
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        nickname=user_data.username,
    )
    db.add(user)
    await db.flush()

    # 标记邀请码已使用
    invitation.is_used = True
    invitation.used_by = user.id
    invitation.used_at = datetime.utcnow()

    await db.commit()
    await db.refresh(user)

    # 生成令牌
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login", response_model=Token, summary="用户登录")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """用户登录（OAuth2 密码模式）"""
    # 支持用户名或邮箱登录
    result = await db.execute(
        select(User).where(
            or_(
                User.username == form_data.username,
                User.email == form_data.username,
            ),
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # 生成令牌
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/login/json", response_model=Token, summary="用户登录（JSON）")
async def login_json(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """用户登录（JSON 格式）"""
    # 支持用户名或邮箱登录
    result = await db.execute(
        select(User).where(
            or_(
                User.username == login_data.username,
                User.email == login_data.username,
            ),
            User.deleted_at == None,
        )
    )
    user = result.scalar_one_or_none()

    if not user or not user.hashed_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow()
    await db.commit()

    # 生成令牌
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=Token, summary="刷新令牌")
async def refresh_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """使用刷新令牌获取新的访问令牌"""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少认证令牌",
        )

    refresh_token_value = auth_header.replace("Bearer ", "")
    user_id = verify_token(refresh_token_value, token_type="refresh")

    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at == None)
    )
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    # 生成新令牌
    new_access_token = create_access_token(data={"sub": str(user.id)})
    new_refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
    )


@router.get("/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """获取当前登录用户信息"""
    return current_user


@router.put("/me", response_model=UserResponse, summary="更新用户信息")
async def update_me(
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前用户信息"""
    if user_data.nickname is not None:
        current_user.nickname = user_data.nickname
    if user_data.avatar_url is not None:
        current_user.avatar_url = user_data.avatar_url

    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.put("/password", summary="修改密码")
async def change_password(
    password_data: PasswordChange,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前用户密码"""
    if not current_user.hashed_password:
        raise HTTPException(status_code=400, detail="第三方登录用户无法修改密码")

    if not verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="旧密码错误")

    current_user.hashed_password = get_password_hash(password_data.new_password)
    await db.commit()

    return {"detail": "密码修改成功"}


@router.post("/logout", summary="用户登出")
async def logout(
    current_user: User = Depends(get_current_user),
):
    """用户登出（客户端应删除本地令牌）"""
    return {"detail": "登出成功"}


# ==================== 邀请码管理（管理员） ====================

@router.post(
    "/invitations",
    response_model=list[InvitationResponse],
    summary="创建邀请码"
)
async def create_invitations(
    invitation_data: InvitationCreate,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """创建邀请码（仅管理员）"""
    invitations = []
    expires_at = None

    if invitation_data.expires_days:
        expires_at = datetime.utcnow() + timedelta(days=invitation_data.expires_days)

    for _ in range(invitation_data.count):
        code = secrets.token_urlsafe(16)[:16].upper()
        invitation = Invitation(
            code=code,
            created_by=current_user.id,
            expires_at=expires_at,
        )
        db.add(invitation)
        invitations.append(invitation)

    await db.commit()

    for inv in invitations:
        await db.refresh(inv)

    return invitations


@router.get(
    "/invitations",
    response_model=list[InvitationResponse],
    summary="获取邀请码列表"
)
async def list_invitations(
    skip: int = 0,
    limit: int = 50,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """获取邀请码列表（仅管理员）"""
    result = await db.execute(
        select(Invitation)
        .order_by(Invitation.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()


@router.delete("/invitations/{invitation_id}", summary="删除邀请码")
async def delete_invitation(
    invitation_id: int,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    """删除邀请码（仅管理员）"""
    result = await db.execute(
        select(Invitation).where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise HTTPException(status_code=404, detail="邀请码不存在")

    if invitation.is_used:
        raise HTTPException(status_code=400, detail="已使用的邀请码无法删除")

    await db.delete(invitation)
    await db.commit()

    return {"detail": "删除成功"}


# ==================== 第三方登录 ====================

from app.services.oauth_service import oauth_service
from app.schemas.user import OAuthAuthorize


@router.get("/github", response_model=OAuthAuthorize, summary="GitHub 登录")
async def github_login():
    """获取 GitHub 授权 URL"""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="GitHub 登录未配置")

    import secrets as _secrets
    state = _secrets.token_urlsafe(16)
    authorize_url = await oauth_service.get_github_authorize_url(state)

    return OAuthAuthorize(authorize_url=authorize_url)


@router.get("/github/callback", summary="GitHub 登录回调")
async def github_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """GitHub 登录回调处理"""
    if not settings.GITHUB_CLIENT_ID or not settings.GITHUB_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail="GitHub 登录未配置")

    # 获取 GitHub 用户信息
    github_user = await oauth_service.exchange_github_code(code)
    if not github_user:
        raise HTTPException(status_code=400, detail="GitHub 授权失败")

    github_id = str(github_user.get("id"))
    email = github_user.get("email")
    username = github_user.get("login")
    avatar_url = github_user.get("avatar_url")
    name = github_user.get("name")

    # 查找或创建用户
    result = await db.execute(
        select(User).where(User.github_id == github_id, User.deleted_at == None)
    )
    user = result.scalar_one_or_none()

    if not user and email:
        # 尝试通过邮箱查找已有用户
        result = await db.execute(
            select(User).where(User.email == email, User.deleted_at == None)
        )
        user = result.scalar_one_or_none()

        if user:
            # 关联 GitHub 账号
            user.github_id = github_id
            if not user.avatar_url:
                user.avatar_url = avatar_url

    if not user:
        # 创建新用户（不需要邀请码）
        user = User(
            username=f"github_{github_id}",
            email=email or f"github_{github_id}@placeholder.local",
            github_id=github_id,
            nickname=name or username,
            avatar_url=avatar_url,
            is_active=True,
        )
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    # 生成令牌
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # 返回 HTML 页面，通过 postMessage 将令牌发送给父窗口
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>登录成功</title></head>
    <body>
    <script>
    (function() {{
        const data = {{
            access_token: '{access_token}',
            refresh_token: '{refresh_token}',
            user: {{
                id: {user.id},
                username: '{user.username}',
                email: '{user.email}',
                nickname: '{user.nickname or ""}',
                avatar_url: '{user.avatar_url or ""}'
            }}
        }};
        if (window.opener) {{
            window.opener.postMessage({{ type: 'oauth-success', data: data }}, '*');
            window.close();
        }} else {{
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/';
        }}
    }})();
    </script>
    <p>登录成功，正在跳转...</p>
    </body>
    </html>
    """

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)


@router.get("/wechat", response_model=OAuthAuthorize, summary="微信登录")
async def wechat_login():
    """获取微信授权 URL"""
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise HTTPException(status_code=400, detail="微信登录未配置")

    import secrets as _secrets
    state = _secrets.token_urlsafe(16)
    authorize_url = await oauth_service.get_wechat_authorize_url(state)

    return OAuthAuthorize(authorize_url=authorize_url)


@router.get("/wechat/callback", summary="微信登录回调")
async def wechat_callback(
    code: str,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """微信登录回调处理"""
    if not settings.WECHAT_APP_ID or not settings.WECHAT_APP_SECRET:
        raise HTTPException(status_code=400, detail="微信登录未配置")

    # 获取微信用户信息
    wechat_user = await oauth_service.exchange_wechat_code(code)
    if not wechat_user:
        raise HTTPException(status_code=400, detail="微信授权失败")

    openid = wechat_user.get("openid")
    unionid = wechat_user.get("unionid")
    nickname = wechat_user.get("nickname")
    avatar_url = wechat_user.get("headimgurl")

    # 查找或创建用户
    result = await db.execute(
        select(User).where(User.wechat_openid == openid, User.deleted_at == None)
    )
    user = result.scalar_one_or_none()

    if not user and unionid:
        # 尝试通过 unionid 查找
        result = await db.execute(
            select(User).where(User.wechat_unionid == unionid, User.deleted_at == None)
        )
        user = result.scalar_one_or_none()

        if user:
            # 关联 openid
            user.wechat_openid = openid

    if not user:
        # 创建新用户（不需要邀请码）
        user = User(
            username=f"wechat_{openid[:12]}",
            email=f"wechat_{openid[:12]}@placeholder.local",
            wechat_openid=openid,
            wechat_unionid=unionid,
            nickname=nickname,
            avatar_url=avatar_url,
            is_active=True,
        )
        db.add(user)
        await db.flush()

    if not user.is_active:
        raise HTTPException(status_code=400, detail="用户已被禁用")

    # 更新最后登录时间
    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)

    # 生成令牌
    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # 返回 HTML 页面
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><title>登录成功</title></head>
    <body>
    <script>
    (function() {{
        const data = {{
            access_token: '{access_token}',
            refresh_token: '{refresh_token}',
            user: {{
                id: {user.id},
                username: '{user.username}',
                email: '{user.email}',
                nickname: '{user.nickname or ""}',
                avatar_url: '{user.avatar_url or ""}'
            }}
        }};
        if (window.opener) {{
            window.opener.postMessage({{ type: 'oauth-success', data: data }}, '*');
            window.close();
        }} else {{
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('refresh_token', data.refresh_token);
            localStorage.setItem('user', JSON.stringify(data.user));
            window.location.href = '/';
        }}
    }})();
    </script>
    <p>登录成功，正在跳转...</p>
    </body>
    </html>
    """

    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html_content)