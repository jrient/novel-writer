"""
OpenAI Provider 实现
"""
import json
import logging
from typing import AsyncGenerator, Optional, Dict, Any

from app.core.config import settings
from app.services.providers.base import BaseLLMProvider, GenerationResult, StreamChunk

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API Provider"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "openai"

    def is_available(self) -> bool:
        """检查 OpenAI 是否可用"""
        return bool(
            settings.OPENAI_API_KEY
            and settings.OPENAI_API_KEY not in ("sk-xxx", "", None)
        )

    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL,
                timeout=600.0,
            )
        return self._client

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.8,
    ) -> GenerationResult:
        """非流式生成"""
        try:
            from openai import RateLimitError, APIConnectionError, APITimeoutError

            client = self._get_client()
            response = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt or self.default_system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return GenerationResult(
                content=response.choices[0].message.content or "",
                tokens_used=response.usage.total_tokens if response.usage else None,
                model=settings.OPENAI_MODEL,
                provider=self.name,
            )

        except RateLimitError as e:
            logger.error(f"OpenAI 速率限制: {e}")
            raise RuntimeError("AI 服务繁忙，请稍后重试")
        except APIConnectionError as e:
            logger.error(f"OpenAI 连接错误: {e}")
            raise RuntimeError("无法连接到 AI 服务")
        except APITimeoutError as e:
            logger.error(f"OpenAI 超时: {e}")
            raise RuntimeError("AI 服务响应超时")
        except Exception as e:
            logger.error(f"OpenAI 未知错误: {e}", exc_info=True)
            raise RuntimeError(f"OpenAI 调用失败: {e}")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 8000,
        temperature: float = 0.8,
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式生成"""
        try:
            from openai import RateLimitError, APIConnectionError, APITimeoutError

            client = self._get_client()
            stream = await client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt or self.default_system_prompt},
                    {"role": "user", "content": prompt},
                ],
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield StreamChunk(text=chunk.choices[0].delta.content)

            yield StreamChunk(text="", done=True)

        except RateLimitError as e:
            logger.error(f"OpenAI 流式生成速率限制: {e}")
            yield StreamChunk(text="", error="AI 服务繁忙，请稍后重试")
        except APIConnectionError as e:
            logger.error(f"OpenAI 流式生成连接错误: {e}")
            yield StreamChunk(text="", error="无法连接到 AI 服务")
        except APITimeoutError as e:
            logger.error(f"OpenAI 流式生成超时: {e}")
            yield StreamChunk(text="", error="AI 服务响应超时")
        except Exception as e:
            logger.error(f"OpenAI 流式生成未知错误: {e}", exc_info=True)
            yield StreamChunk(text="", error=str(e))