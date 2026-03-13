"""
Token 使用记录服务
"""
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token_usage import TokenUsage

logger = logging.getLogger(__name__)


async def log_token_usage(
    db: AsyncSession,
    user_id: int,
    provider: str,
    model: str,
    action: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    project_id: Optional[int] = None,
) -> None:
    """记录一次 AI 调用的 token 使用量"""
    try:
        usage = TokenUsage(
            user_id=user_id,
            project_id=project_id,
            provider=provider,
            model=model,
            action=action,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
        db.add(usage)
        await db.commit()
    except Exception as e:
        logger.error(f"记录 token 使用失败: {e}")
        # 不影响主流程，静默回滚
        await db.rollback()


def estimate_tokens(text: str) -> int:
    """粗略估算中文文本的 token 数（中文约 1.5 字符/token）"""
    if not text:
        return 0
    # 中文字符按 1.5 char/token，英文按 4 char/token，取混合估算
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars / 4)
