"""theme_classifier 单元测试"""
from pathlib import Path
import pytest

from script_rubric.pipeline.theme_classifier import classify, load_config

CONFIG_PATH = Path(__file__).parent.parent / "config" / "theme_classification.yaml"


def test_override_exact_match():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("改编Ai真人剧《谋妃千岁》大纲小传前三集", text_content="", config=cfg)
    assert theme == "ai_realperson"
    assert st == "explanatory"


def test_keyword_ai_realperson_not_in_override():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("原创AI仿真人短剧《未知新稿》", text_content="", config=cfg)
    assert theme == "ai_realperson"
    assert st == "explanatory"


def test_keyword_xianxia_requires_content_check():
    cfg = load_config(CONFIG_PATH)
    # Title with "神" but no xianxia content → should NOT trigger xianxia
    theme, st = classify("《神秘的邻居》", text_content="这是一个都市故事，主角开公司。", config=cfg)
    assert theme != "xianxia" or st != "dynamic"

    # Title + xianxia content → trigger xianxia (title must also have keyword "仙")
    theme2, st2 = classify("《无名仙尊》", text_content="他突破到了金仙境界，法宝光芒大作。炼丹炉火焰翻涌。", config=cfg)
    assert theme2 == "xianxia"
    assert st2 == "dynamic"


def test_unknown_defaults_to_none():
    cfg = load_config(CONFIG_PATH)
    theme, st = classify("完全不认识的标题", text_content="完全不相关内容", config=cfg)
    assert theme is None
    assert st is None
