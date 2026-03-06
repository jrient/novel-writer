"""
Embedding服务
调用API生成文本向量
"""
import os
import httpx
from typing import List, Optional
from app.core.config import settings


def _get_proxy() -> Optional[str]:
    """从环境变量获取代理配置"""
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None


class EmbeddingService:
    def __init__(self):
        self.api_base = settings.EMBEDDING_API_BASE
        self.api_key = settings.EMBEDDING_API_KEY
        self.model = settings.EMBEDDING_MODEL

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量生成embedding向量"""
        proxy = _get_proxy()
        async with httpx.AsyncClient(timeout=60.0, proxy=proxy, verify=False) as client:
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

    async def generate_embedding(self, text: str) -> List[float]:
        """生成单个文本的embedding"""
        embeddings = await self.generate_embeddings([text])
        return embeddings[0]


embedding_service = EmbeddingService()
