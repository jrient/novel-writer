"""StyleGuard 服务单元测试"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def sample_dir(tmp_path):
    """创建临时样本目录"""
    dynamic_samples = {
        "script_type": "dynamic",
        "samples": [
            {"title": "剧本A", "excerpt": "△张总猛拍桌，文件飞散。"},
            {"title": "剧本B", "excerpt": "△李秘书推门而入，脸色铁青。"},
            {"title": "剧本C", "excerpt": "△王老板摔门而去，茶杯震翻在地。"},
        ],
        "golden_quotes": [
            "张总（暴怒）：三十万！你敢说不知道？！",
            "△李秘书冷笑一声，把文件甩在桌上。",
            "王老板（颤抖）：我……我以为你会懂。",
            "△她眼眶红了，没说话。",
        ],
    }
    explanatory_samples = {
        "script_type": "explanatory",
        "samples": [
            {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。"},
        ],
        "golden_quotes": [
            "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
            "我扶着门框的手指骨节泛白，指甲死死抠进木头里。",
        ],
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
    assert len(samples) == 1  # 默认返回 1 段
    assert isinstance(samples[0], str)
    assert len(samples[0]) > 0


def test_style_guard_loads_explanatory_samples(sample_dir):
    """StyleGuard 加载解说漫范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("explanatory")
    assert len(samples) == 1
    assert isinstance(samples[0], str)


def test_style_guard_random_rotation(sample_dir):
    """get_style_samples(count=2) 随机返回不同样本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    results = set()
    for _ in range(10):
        samples = sg.get_style_samples("dynamic", count=2)
        results.add(tuple(samples))
    # 至少有 2 种不同组合
    assert len(results) >= 2


def test_style_guard_returns_all_when_count_exceeds(sample_dir):
    """count 超过样本数时返回全部"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic", count=10)
    assert len(samples) == 3  # 只有 3 段样本


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
    # 验证包含关键条目
    assert "比喻" in rules or "暗喻" in rules
    assert "情绪" in rules


def test_style_guard_build_style_context(sample_dir):
    """build_style_context 组合范本+金句为 <examples> 块"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    context = sg.build_style_context("dynamic")
    assert "<examples>" in context
    assert "</examples>" in context
    assert "节奏" in context or "句式" in context  # 包含引导语


def test_style_guard_missing_file(sample_dir):
    """不存在的 script_type 回退到 dynamic 数据"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    # unknown_type 回退到 dynamic，所以有数据
    samples = sg.get_style_samples("unknown_type")
    assert len(samples) == 1
    assert isinstance(samples[0], str)
    # empty script_type 也回退到 dynamic
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
