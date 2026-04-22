"""
Episode content prompt 三层结构集成测试
验证反 AI 味清单和范本注入正确工作
"""
import json
import re
from unittest.mock import patch

import pytest


class TestAntiSlopInjection:
    """反 AI 味清单注入测试"""

    def test_anti_slop_rules_in_system_prompt(self):
        """system prompt 包含反 AI 味清单"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard()
        rules = sg.get_anti_slop_rules()

        assert "写作禁忌" in rules
        assert "比喻" in rules or "暗喻" in rules
        assert "情绪" in rules
        assert "万能动词" in rules or "感到" in rules
        assert "排比" in rules
        assert "心理描写" in rules

    def test_anti_slop_rules_count(self):
        """反 AI 味清单有 9 条"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard()
        rules = sg.get_anti_slop_rules()
        items = re.findall(r"^\d+\.", rules, re.MULTILINE)
        assert len(items) == 9


class TestStyleContextInjection:
    """范本+金句注入测试"""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """创建测试用样本目录"""
        dynamic_samples = {
            "script_type": "dynamic",
            "samples": [
                {"title": "剧本A", "excerpt": "△张总猛拍桌，文件飞散。\n张总（暴怒）：三十万！公司账上的三十万！"},
            ],
            "golden_quotes": [
                "△她眼眶红了，没说话。",
                "张总（暴怒）：三十万！你敢说不知道？！",
            ],
        }
        explanatory_samples = {
            "script_type": "explanatory",
            "samples": [
                {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。"},
            ],
            "golden_quotes": [
                "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
            ],
        }
        (tmp_path / "style_samples_dynamic.json").write_text(
            json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "style_samples_explanatory.json").write_text(
            json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
        )
        return tmp_path

    def test_build_style_context_contains_examples(self, sample_dir):
        """build_style_context 返回包含范本和金句的 <examples> 块"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(sample_dir))
        ctx = sg.build_style_context("dynamic")

        assert "<examples>" in ctx
        assert "</examples>" in ctx
        # get_style_samples 返回 excerpt 字符串，不包含 title
        assert "张总猛拍桌" in ctx
        assert "三十万" in ctx
        assert "参考" in ctx  # "金句/句式参考"
        assert "节奏" in ctx  # 引导语 "模仿其节奏"

    def test_build_style_context_explanatory(self, sample_dir):
        """解说漫 build_style_context 返回正确内容"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(sample_dir))
        ctx = sg.build_style_context("explanatory")

        assert "<examples>" in ctx
        # get_style_samples 返回 excerpt 字符串
        assert "快递员敲门" in ctx
        assert "骨头缝" in ctx

    def test_build_style_context_empty_when_no_samples_or_quotes(self, tmp_path):
        """没有样本和金句时 build_style_context 返回空字符串"""
        from app.services.style_guard import StyleGuard

        # 创建空的文件（script_type 存在但无 samples/golden_quotes）
        (tmp_path / "style_samples_dynamic.json").write_text(
            json.dumps({"script_type": "dynamic", "samples": [], "golden_quotes": []}, ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "style_samples_explanatory.json").write_text(
            json.dumps({"script_type": "explanatory", "samples": [], "golden_quotes": []}, ensure_ascii=False), encoding="utf-8"
        )
        sg = StyleGuard(samples_dir=str(tmp_path))
        assert sg.build_style_context("dynamic") == ""
        assert sg.build_style_context("explanatory") == ""
        # unknown 类型 fallback 到 dynamic，也是空
        assert sg.build_style_context("unknown") == ""

    def test_build_style_context_without_files(self):
        """没有样本文件时 build_style_context 返回空字符串"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir="/nonexistent/path")
        ctx = sg.build_style_context("dynamic")
        assert ctx == ""


class TestPromptStructure:
    """Prompt 结构验证测试"""

    def test_dynamic_episode_prompt_has_all_layers(self):
        """动态漫 episode_content prompt 包含规则层"""
        from app.services.script_ai_service import DYNAMIC_PROMPTS

        sys_prompt = DYNAMIC_PROMPTS["episode_content"]["system"]
        user_prompt = DYNAMIC_PROMPTS["episode_content"]["user"]

        assert len(sys_prompt) > 50
        assert len(user_prompt) > 100

    def test_explanatory_episode_prompt_has_format(self):
        """解说漫 episode_content prompt 包含格式要求"""
        from app.services.script_ai_service import EXPLANATORY_PROMPTS

        sys_prompt = EXPLANATORY_PROMPTS["episode_content"]["system"]
        user_prompt = EXPLANATORY_PROMPTS["episode_content"]["user"]

        assert "△" in user_prompt  # 动作标记
        assert "{episode_number}-1" in user_prompt  # 分场号格式


class TestHelperFunctions:
    """_build_episode_system_prompt 和 _build_episode_user_prompt 测试"""

    @pytest.fixture
    def sample_dir(self, tmp_path):
        """创建测试用样本目录"""
        dynamic_samples = {
            "script_type": "dynamic",
            "samples": [
                {"title": "剧本A", "excerpt": "△张总猛拍桌，文件飞散。"},
            ],
            "golden_quotes": ["△她眼眶红了，没说话。"],
        }
        explanatory_samples = {
            "script_type": "explanatory",
            "samples": [],
            "golden_quotes": [],
        }
        (tmp_path / "style_samples_dynamic.json").write_text(
            json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
        )
        (tmp_path / "style_samples_explanatory.json").write_text(
            json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
        )
        return tmp_path

    def test_build_episode_system_prompt_adds_anti_slop(self, sample_dir):
        """_build_episode_system_prompt 在 system prompt 末尾追加反 AI 味清单"""
        from app.services.script_ai_service import _build_episode_system_prompt

        result = _build_episode_system_prompt("原始规则", "dynamic")
        assert "原始规则" in result
        assert "写作禁忌" in result
        # 反 AI 味清单应该在后面
        anti_slop_pos = result.find("写作禁忌")
        orig_pos = result.find("原始规则")
        assert anti_slop_pos > orig_pos

    def test_build_episode_user_prompt_adds_examples(self, sample_dir):
        """_build_episode_user_prompt 在 user prompt 末尾追加 <examples>"""
        from app.services.style_guard import StyleGuard
        from app.services.script_ai_service import _build_episode_user_prompt

        # Mock get_style_guard to use our temp directory
        temp_sg = StyleGuard(samples_dir=str(sample_dir))
        with patch("app.services.style_guard.get_style_guard", return_value=temp_sg):
            result = _build_episode_user_prompt("原始指令", "dynamic")

        assert "原始指令" in result
        assert "<examples>" in result
        assert "</examples>" in result

    def test_build_episode_user_prompt_no_samples_returns_original(self, sample_dir):
        """没有样本文件时 _build_episode_user_prompt 返回原始 prompt"""
        from app.services.style_guard import StyleGuard
        from app.services.script_ai_service import _build_episode_user_prompt

        sg_dir = "/nonexistent/path"
        temp_sg = StyleGuard(samples_dir=sg_dir)
        style_ctx = temp_sg.build_style_context("dynamic")
        assert style_ctx == ""  # 确认空

        with patch("app.services.style_guard.get_style_guard", return_value=temp_sg):
            result = _build_episode_user_prompt("原始指令", "dynamic")

        assert result == "原始指令"
