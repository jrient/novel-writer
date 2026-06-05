"""
Embedding服务
调用API生成文本向量
"""
import asyncio
import logging
import httpx
from typing import List, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# 瞬时故障重试参数：yibuapi 偶发 503 / ConnectError / 超时，退避重试可消化
_MAX_RETRIES = 3          # 总尝试次数 = 1 + 重试
_BACKOFF_BASE = 0.6       # 退避基数（秒），第 n 次重试等待 _BACKOFF_BASE * 2**(n-1)




def _is_transient(exc: Exception) -> bool:
    """判定是否为可重试的瞬时故障：连接/超时类，或 5xx / 429。
    4xx（鉴权、参数错）不重试——重试也不会好。
    """
    if isinstance(exc, (httpx.ConnectError, httpx.ReadError, httpx.WriteError,
                        httpx.TimeoutException, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code < 600
    return False


class EmbeddingService:
    def __init__(self):
        self.api_base = settings.EMBEDDING_API_BASE
        self.api_key = settings.EMBEDDING_API_KEY
        self.model = settings.EMBEDDING_MODEL

    async def _post_once(self, texts: List[str]) -> List[List[float]]:
        # trust_env=True 让 httpx 遵守 HTTP_PROXY 与 NO_PROXY；yibuapi 在 NO_PROXY 中会直连，避免被翻墙代理卡死
        async with httpx.AsyncClient(timeout=60.0, trust_env=True) as client:
            response = await client.post(
                f"{self.api_base}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.model,
                    "input": texts
                }
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量生成embedding向量。瞬时故障（5xx/429/连接超时）指数退避重试。"""
        last_exc: Optional[Exception] = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return await self._post_once(texts)
            except Exception as exc:  # noqa: BLE001 — 由 _is_transient 区分是否重试
                last_exc = exc
                if attempt >= _MAX_RETRIES or not _is_transient(exc):
                    raise
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "embedding 请求瞬时失败（第 %d/%d 次）：%s: %s，%.1fs 后重试",
                    attempt, _MAX_RETRIES, type(exc).__name__, str(exc)[:120], wait,
                )
                await asyncio.sleep(wait)
        # 理论不可达：循环要么 return 要么 raise
        raise last_exc  # type: ignore[misc]

    async def generate_embedding(self, text: str) -> List[float]:
        """生成单个文本的embedding"""
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]


embedding_service = EmbeddingService()
