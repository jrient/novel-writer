"""
飞书 Docx 正文拉取（带本地缓存）
================================

剧本正文以 Docx mention 形式存储在飞书多维表格的「书名/文本」字段。
本模块负责按 docx_token 拉取 raw_content 并缓存到 script_rubric/data/docx_cache/。

设计要点：
- 缓存以 token 命名（{token}.txt），命中即跳过 API 调用
- force=True 时强制刷新
- 单次 sync 失败的 token 列入 failed_tokens 显式报告，不静默吞错
"""

from __future__ import annotations

import logging
from pathlib import Path

from data.feishu_common import fetch_docx_raw_content, get_tenant_access_token
from script_rubric.config import DATA_DIR

logger = logging.getLogger(__name__)

DOCX_CACHE_DIR = DATA_DIR / "docx_cache"


def _cache_path(docx_token: str) -> Path:
    return DOCX_CACHE_DIR / f"{docx_token}.txt"


def load_cached(docx_token: str) -> str | None:
    p = _cache_path(docx_token)
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8")
            return content if content else None
        except Exception:
            return None
    return None


def save_cache(docx_token: str, content: str) -> None:
    DOCX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(docx_token).write_text(content, encoding="utf-8")


def fetch_one(token: str, docx_token: str, force: bool = False) -> tuple[str | None, str | None]:
    """拉取单个 docx 正文。

    Returns:
        (content, error)：成功时 content 非空 error=None；失败时 content=None error=描述
    """
    if not force:
        cached = load_cached(docx_token)
        if cached is not None:
            return cached, None

    try:
        content = fetch_docx_raw_content(token, docx_token)
        if content:
            save_cache(docx_token, content)
            return content, None
        return None, "empty content returned"
    except Exception as e:
        return None, str(e)


def fetch_many(
    docx_tokens: list[str],
    force: bool = False,
) -> tuple[dict[str, str], dict[str, str]]:
    """批量拉取多个 docx token。

    Returns:
        (success_map, failed_map)
        success_map: {docx_token: content}
        failed_map:  {docx_token: error_msg}
    """
    if not docx_tokens:
        return {}, {}

    # 仅在需要 API 时获取 tenant token（缓存命中时不必拉）
    tenant_token: str | None = None
    success: dict[str, str] = {}
    failed: dict[str, str] = {}

    unique_tokens = list(dict.fromkeys(docx_tokens))  # 去重保序
    logger.info(f"docx fetch: {len(unique_tokens)} unique tokens (force={force})")

    for dt in unique_tokens:
        if not force:
            cached = load_cached(dt)
            if cached is not None:
                success[dt] = cached
                continue

        if tenant_token is None:
            try:
                tenant_token = get_tenant_access_token()
            except Exception as e:
                # 整批 fail
                for tk in unique_tokens:
                    if tk not in success:
                        failed[tk] = f"tenant token error: {e}"
                return success, failed

        content, err = fetch_one(tenant_token, dt, force=force)
        if content is not None:
            success[dt] = content
        else:
            failed[dt] = err or "unknown error"

    logger.info(f"docx fetch done: success={len(success)}, failed={len(failed)}")
    return success, failed
