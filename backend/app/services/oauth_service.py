"""
OAuth 服务 - GitHub 和微信第三方登录
"""
import httpx
from typing import Optional
from urllib.parse import urlencode

from app.core.config import settings


class OAuthService:
    """OAuth 服务基类"""

    @staticmethod
    async def get_github_authorize_url(state: str) -> str:
        """获取 GitHub 授权 URL"""
        params = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": settings.GITHUB_REDIRECT_URI,
            "scope": "read:user user:email",
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    @staticmethod
    async def exchange_github_code(code: str) -> Optional[dict]:
        """使用授权码换取 GitHub 访问令牌"""
        async with httpx.AsyncClient() as client:
            # 获取 access_token
            token_response = await client.post(
                "https://github.com/login/oauth/access_token",
                json={
                    "client_id": settings.GITHUB_CLIENT_ID,
                    "client_secret": settings.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.GITHUB_REDIRECT_URI,
                },
                headers={"Accept": "application/json"},
            )

            token_data = token_response.json()
            if "error" in token_data:
                return None

            access_token = token_data.get("access_token")
            if not access_token:
                return None

            # 获取用户信息
            user_response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )

            user_data = user_response.json()

            # 获取用户邮箱（如果未公开）
            if not user_data.get("email"):
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
                emails = email_response.json()
                primary_email = next(
                    (e for e in emails if e.get("primary")),
                    emails[0] if emails else None
                )
                if primary_email:
                    user_data["email"] = primary_email.get("email")

            return user_data

    @staticmethod
    async def get_wechat_authorize_url(state: str) -> str:
        """获取微信授权 URL"""
        params = {
            "appid": settings.WECHAT_APP_ID,
            "redirect_uri": settings.WECHAT_REDIRECT_URI,
            "response_type": "code",
            "scope": "snsapi_login",
            "state": state,
        }
        return f"https://open.weixin.qq.com/connect/qrconnect?{urlencode(params)}#wechat_redirect"

    @staticmethod
    async def exchange_wechat_code(code: str) -> Optional[dict]:
        """使用授权码换取微信访问令牌和用户信息"""
        async with httpx.AsyncClient() as client:
            # 获取 access_token
            token_response = await client.get(
                "https://api.weixin.qq.com/sns/oauth2/access_token",
                params={
                    "appid": settings.WECHAT_APP_ID,
                    "secret": settings.WECHAT_APP_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )

            token_data = token_response.json()
            if "errcode" in token_data:
                return None

            access_token = token_data.get("access_token")
            openid = token_data.get("openid")
            unionid = token_data.get("unionid")

            if not access_token or not openid:
                return None

            # 获取用户信息
            user_response = await client.get(
                "https://api.weixin.qq.com/sns/userinfo",
                params={
                    "access_token": access_token,
                    "openid": openid,
                },
            )

            user_data = user_response.json()
            if "errcode" in user_data:
                return None

            user_data["openid"] = openid
            user_data["unionid"] = unionid

            return user_data


oauth_service = OAuthService()