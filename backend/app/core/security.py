"""
安全工具模块 - JWT Token 和密码处理
"""
import threading
from datetime import datetime, timedelta
from typing import Optional, Set

from jose import jwt, JWTError
import bcrypt

from app.core.config import settings

# Token 黑名单（内存存储，重启后清空 — 可接受，因为 token 也会过期）
_token_blacklist: Set[str] = set()
_blacklist_lock = threading.Lock()


def blacklist_token(token: str):
    """将 token 加入黑名单"""
    with _blacklist_lock:
        _token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """检查 token 是否在黑名单中"""
    return token in _token_blacklist


def cleanup_blacklist():
    """清理黑名单中已过期的 token（可定期调用）"""
    with _blacklist_lock:
        expired = set()
        for token in _token_blacklist:
            payload = decode_token(token)
            if payload is None:  # 解码失败说明已过期
                expired.add(token)
        _token_blacklist -= expired


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return bcrypt.checkpw(
        plain_password.encode('utf-8'),
        hashed_password.encode('utf-8') if isinstance(hashed_password, str) else hashed_password
    )


def get_password_hash(password: str) -> str:
    """生成密码哈希"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """创建刷新令牌"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(
        to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """解码令牌"""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        return payload
    except JWTError:
        return None


def verify_token(token: str, token_type: str = "access") -> Optional[int]:
    """验证令牌并返回用户ID"""
    if is_token_blacklisted(token):
        return None
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != token_type:
        return None
    user_id: Optional[int] = payload.get("sub")
    if user_id is None:
        return None
    return int(user_id)