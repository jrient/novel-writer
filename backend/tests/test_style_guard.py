"""StyleGuard 服务单元测试"""
import json
from pathlib import Path

import pytest


@pytest.fixture
def sample_dir(tmp_path):
    dynamic_samples = {
        "script_type": "dynamic",
        "samples": [
            {"title": "剧A", "excerpt": "△张总猛拍桌。", "genre": "男频", "theme_tag": "xianxia"},
            {"title": "剧B", "excerpt": "△李秘书推门。", "genre": "男频", "theme_tag": "xianxia"},
            {"title": "剧C", "excerpt": "△王老板摔门。", "genre": "女频", "theme_tag": "urban"},
        ],
        "golden_quotes": ["张总（暴怒）：三十万！你敢说不知道？！"],
    }
    explanatory_samples = {
        "script_type": "explanatory",
        "samples": [
            {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。", "genre": "世情", "theme_tag": "urban"},
            {"title": "蚀骨之恨", "excerpt": "△丈夫和妹妹在灵堂上苟合。", "genre": "女频", "theme_tag": "rebirth_modern"},
            {"title": "男友全家", "excerpt": "△许妍关门。", "genre": "女频", "theme_tag": "family"},
        ],
        "golden_quotes": ["门刚拉开一条缝。"],
    }
    (tmp_path / "style_samples_dynamic.json").write_text(
        json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "style_samples_explanatory.json").write_text(
        json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_style_guard_loads_dynamic_samples(sample_dir):
    """StyleGuard 加载动态漫范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic")
    assert len(samples) == 1
    assert isinstance(samples[0], dict)
    assert "excerpt" in samples[0]
    assert "genre" in samples[0]


def test_style_guard_loads_explanatory_samples(sample_dir):
    """StyleGuard 加载解说漫范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("explanatory")
    assert len(samples) == 1
    assert isinstance(samples[0], dict)


def test_style_guard_random_rotation(sample_dir):
    """get_style_samples(count=2) 随机返回不同样本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    results = set()
    for _ in range(10):
        samples = sg.get_style_samples("dynamic", count=2)
        results.add(tuple(s["title"] for s in samples))
    assert len(results) >= 2


def test_style_guard_returns_all_when_count_exceeds(sample_dir):
    """count 超过样本数时返回全部"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic", count=10)
    assert len(samples) == 3


def test_style_guard_get_golden_quotes(sample_dir):
    """get_golden_quotes 返回金句列表"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    quotes = sg.get_golden_quotes("dynamic")
    assert len(quotes) > 0
    assert isinstance(quotes, list)
    assert all(isinstance(q, str) for q in quotes)


def test_style_guard_get_anti_slop_rules():
    """get_anti_slop_rules 返回 9 条反 AI 味清单"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard()
    rules = sg.get_anti_slop_rules()
    assert isinstance(rules, str)
    assert len(rules) > 100
    assert "比喻" in rules or "暗喻" in rules
    assert "情绪" in rules


def test_style_guard_build_style_context(sample_dir):
    """build_style_context 组合范本+金句为 <examples> 块"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    context = sg.build_style_context("dynamic")
    assert "<examples>" in context
    assert "</examples>" in context
    assert "节奏" in context or "句式" in context


def test_style_guard_genre_preference(sample_dir):
    """同 genre 优先返回"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    seen_titles = set()
    for _ in range(30):
        got = sg.get_style_samples("explanatory", count=1, genre="女频")
        seen_titles.add(got[0]["title"])
    assert seen_titles.issubset({"蚀骨之恨", "男友全家"})


def test_style_guard_fallback_when_no_genre_match(sample_dir):
    """未知 genre 回退到同 script_type 全池"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    got = sg.get_style_samples("explanatory", count=3, genre="完全不存在的类")
    assert len(got) == 3


def test_style_guard_backward_compat_no_genre(sample_dir):
    """不带 genre 调用仍然工作"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    got = sg.get_style_samples("dynamic", count=2)
    assert len(got) == 2
    assert all(isinstance(s, dict) for s in got)


def test_build_style_context_with_genre(sample_dir):
    """build_style_context 带 genre 时返回同 genre 范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    ctx = sg.build_style_context("explanatory", genre="女频")
    assert ("蚀骨之恨" in ctx) or ("男友全家" in ctx)


def test_style_guard_missing_file(sample_dir):
    """不存在的 script_type 回退到 dynamic 数据"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("unknown_type")
    assert len(samples) == 1
    assert isinstance(samples[0], dict)
    quotes = sg.get_golden_quotes("unknown_type")
    assert len(quotes) > 0


def test_style_guard_default_dir_not_crash():
    """使用默认目录且文件不存在时不崩溃"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard()
    samples = sg.get_style_samples("dynamic")
    assert isinstance(samples, list)
    quotes = sg.get_golden_quotes("dynamic")
    assert isinstance(quotes, list)
    rules = sg.get_anti_slop_rules()
    assert isinstance(rules, str)
