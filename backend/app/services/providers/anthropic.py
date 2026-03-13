"""
Anthropic Claude Provider 实现
"""
import json
import logging
from typing import AsyncGenerator, Optional, Dict, Any

from app.core.config import settings
from app.services.providers.base import BaseLLMProvider, GenerationResult, StreamChunk

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API Provider"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self._client = None

    @property
    def name(self) -> str:
        return "anthropic"

    def is_available(self) -> bool:
        """检查 Anthropic 是否可用"""
        return bool(
            settings.ANTHROPIC_API_KEY
            and settings.ANTHROPIC_API_KEY not in ("sk-ant-xxx", "", None)
        )

    def _get_client(self):
        """延迟初始化客户端"""
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=settings.ANTHROPIC_API_KEY,
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
            from anthropic import RateLimitError, APIConnectionError, APITimeoutError

            client = self._get_client()
            response = await client.messages.create(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                system=system_prompt or self.default_system_prompt,
                temperature=temperature,
            )

            return GenerationResult(
                content=response.content[0].text if response.content else "",
                tokens_used=response.usage.input_tokens + response.usage.output_tokens if response.usage else None,
                model=settings.ANTHROPIC_MODEL,
                provider=self.name,
            )

        except RateLimitError as e:
            logger.error(f"Anthropic 速率限制: {e}")
            raise RuntimeError("AI 服务繁忙，请稍后重试")
        except APIConnectionError as e:
            logger.error(f"Anthropic 连接错误: {e}")
            raise RuntimeError("无法连接到 AI 服务")
        except APITimeoutError as e:
            logger.error(f"Anthropic 超时: {e}")
            raise RuntimeError("AI 服务响应超时")
        except Exception as e:
            logger.error(f"Anthropic 未知错误: {e}", exc_info=True)
            raise RuntimeError(f"Anthropic 调用失败: {e}")

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 8000,
        temperature: float = 0.8,
    ) -> AsyncGenerator[StreamChunk, None]:
        """流式生成"""
        try:
            from anthropic import RateLimitError, APIConnectionError, APITimeoutError

            client = self._get_client()

            async with client.messages.stream(
                model=settings.ANTHROPIC_MODEL,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                system=system_prompt or self.default_system_prompt,
                temperature=temperature,
            ) as stream:
                async for text in stream.text_stream:
                    yield StreamChunk(text=text)

            yield StreamChunk(text="", done=True)

        except RateLimitError as e:
            logger.error(f"Anthropic 流式生成速率限制: {e}")
            yield StreamChunk(text="", error="AI 服务繁忙，请稍后重试")
        except APIConnectionError as e:
            logger.error(f"Anthropic 流式生成连接错误: {e}")
            yield StreamChunk(text="", error="无法连接到 AI 服务")
        except APITimeoutError as e:
            logger.error(f"Anthropic 流式生成超时: {e}")
            yield StreamChunk(text="", error="AI 服务响应超时")
        except Exception as e:
            logger.error(f"Anthropic 流式生成未知错误: {e}", exc_info=True)
            yield StreamChunk(text="", error=str(e))