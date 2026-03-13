"""
AI Provider 抽象接口
使用策略模式，使业务逻辑与具体厂商 SDK 脱钩
"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class GenerationResult:
    """生成结果"""
    content: str
    tokens_used: Optional[int] = None
    model: Optional[str] = None
    provider: Optional[str] = None


@dataclass
class StreamChunk:
    """流式生成块"""
    text: str
    done: bool = False
    error: Optional[str] = None


class BaseLLMProvider(ABC):
    """
    LLM Provider 基类
    所有 AI 提供商实现都需要继承此类
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4000,
        temperature: float = 0.8,
    ) -> GenerationResult:
        """
        非流式生成

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            max_tokens: 最大 token 数
            temperature: 温度参数

        Returns:
            GenerationResult: 生成结果
        """
        pass

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 8000,
        temperature: float = 0.8,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        流式生成

        Args:
            prompt: 用户提示
            system_prompt: 系统提示
            max_tokens: 最大 token 数
            temperature: 温度参数

        Yields:
            StreamChunk: 流式生成块
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        检查 Provider 是否可用

        Returns:
            bool: 是否可用
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider 名称

        Returns:
            str: 名称
        """
        pass

    @property
    def default_system_prompt(self) -> str:
        """
        默认系统提示

        Returns:
            str: 系统提示
        """
        return "你是一位专业的中文小说创作助手，擅长各类文学创作。"