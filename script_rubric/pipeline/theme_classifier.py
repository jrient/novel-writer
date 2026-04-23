"""主题分类器：把剧本标题 + 正文映射到 (theme_tag, script_type)

优先级：
1. overrides 里精确匹配的标题 → 直接使用
2. keyword_rules 按顺序检查；规则命中关键字后，若 content_check=true 还需 text_content 也命中才生效
3. 都未命中 → (None, None)
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


def load_config(path: Path) -> dict:
    """从 yaml 读取配置"""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify(title: str, text_content: str, config: dict) -> tuple[Optional[str], Optional[str]]:
    """返回 (theme_tag, script_type)；都为 None 表示无法分类"""
    overrides = config.get("overrides") or {}
    if title in overrides:
        o = overrides[title]
        return o.get("theme_tag"), o.get("script_type")

    content_lower = text_content or ""
    for rule in config.get("keyword_rules") or []:
        keywords = rule.get("keywords") or []
        hit_title = any(k in title for k in keywords)
        if not hit_title:
            continue
        if rule.get("content_check"):
            hit_content = any(k in content_lower for k in keywords)
            if not hit_content:
                continue
        return rule.get("theme_tag"), rule.get("script_type")

    return None, None
