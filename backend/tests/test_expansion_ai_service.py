"""
单元测试 - 扩写 AI 服务
测试纯函数，不需要 mock
"""
import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.expansion_ai_service import (
    ExpansionAIService,
    EXPANSION_MULTIPLIERS,
    EXPANSION_LEVEL_NAMES,
)


class TestIsTruncated:
    """测试截断检测函数"""

    def test_finish_reason_length(self):
        """finish_reason 为 'length' 时应返回 True"""
        assert ExpansionAIService._is_truncated("任意文本", "length") is True

    def test_finish_reason_stop(self):
        """finish_reason 为 'stop' 时应返回 False"""
        assert ExpansionAIService._is_truncated("任意文本", "stop") is False

    def test_normal_ending(self):
        """正常结尾（句号结尾）应返回 False"""
        assert ExpansionAIService._is_truncated("这是一段完整的文本。") is False

    def test_normal_ending_with_exclamation(self):
        """感叹号结尾应返回 False"""
        assert ExpansionAIService._is_truncated("这是一段完整的文本！") is False

    def test_normal_ending_with_question(self):
        """问号结尾应返回 False"""
        assert ExpansionAIService._is_truncated("这是一段完整的文本？") is False

    def test_truncated_comma(self):
        """逗号结尾应返回 True（截断）"""
        assert ExpansionAIService._is_truncated("这是一段被截断的文本，") is True

    def test_truncated_comma_ascii(self):
        """英文逗号结尾应返回 True"""
        assert ExpansionAIService._is_truncated("This is truncated,") is True

    def test_truncated_ellipsis(self):
        """省略号结尾应返回 True"""
        assert ExpansionAIService._is_truncated("这是一段被截断的文本……") is True

    def test_truncated_dots(self):
        """英文省略号结尾应返回 True"""
        assert ExpansionAIService._is_truncated("This is truncated...") is True

    def test_no_punctuation(self):
        """无标点结尾应返回 True"""
        assert ExpansionAIService._is_truncated("这是一段被截断的文本") is True

    def test_empty_text(self):
        """空文本应返回 False"""
        assert ExpansionAIService._is_truncated("") is False

    def test_with_quote_ending(self):
        """引号结尾的完整句子应返回 False"""
        assert ExpansionAIService._is_truncated('他说："你好。"') is False

    def test_with_parenthesis_ending(self):
        """括号结尾的完整句子应返回 False"""
        assert ExpansionAIService._is_truncated("这是一个说明（注释）。") is False


class TestDetectScriptMarkers:
    """测试剧本标记检测函数"""

    def test_os_marker(self):
        """检测 OS 标记"""
        assert ExpansionAIService.detect_script_markers("这是旁白 OS 的内容") is True

    def test_os_marker_with_parens(self):
        """检测带括号的 OS 标记"""
        assert ExpansionAIService.detect_script_markers("(OS) 画外音") is True

    def test_action_marker(self):
        """检测△动作标记"""
        assert ExpansionAIService.detect_script_markers("△ 他站了起来") is True

    def test_bracket_marker(self):
        """检测【】场景/角色标记"""
        assert ExpansionAIService.detect_script_markers("【第一场】") is True

    def test_bracket_character(self):
        """检测【】角色名标记"""
        assert ExpansionAIService.detect_script_markers("【张三】你好") is True

    def test_no_markers(self):
        """无剧本标记的普通文本"""
        assert ExpansionAIService.detect_script_markers("这是一段普通的小说文本。") is False

    def test_no_markers_narrative(self):
        """无剧本标记的叙事文本"""
        assert ExpansionAIService.detect_script_markers(
            "张三走进了房间，环顾四周，发现一切都没有改变。"
        ) is False

    def test_empty_text(self):
        """空文本应返回 False"""
        assert ExpansionAIService.detect_script_markers("") is False

    def test_none_text(self):
        """None 应返回 False"""
        assert ExpansionAIService.detect_script_markers(None) is False

    def test_multiple_markers(self):
        """包含多个标记"""
        assert ExpansionAIService.detect_script_markers(
            "【第一场】\n△ 张三走进房间\n张三(OS)内心独白"
        ) is True


class TestExpansionLevels:
    """测试扩写级别常量"""

    def test_all_levels_defined(self):
        """验证三个扩写级别都存在"""
        assert "light" in EXPANSION_MULTIPLIERS
        assert "medium" in EXPANSION_MULTIPLIERS
        assert "deep" in EXPANSION_MULTIPLIERS

    def test_level_values(self):
        """验证扩写级别值"""
        assert EXPANSION_MULTIPLIERS["light"] == 1.5
        assert EXPANSION_MULTIPLIERS["medium"] == 2.0
        assert EXPANSION_MULTIPLIERS["deep"] == 3.0

    def test_level_names(self):
        """验证扩写级别名称"""
        assert EXPANSION_LEVEL_NAMES["light"] == "轻度扩写"
        assert EXPANSION_LEVEL_NAMES["medium"] == "中度扩写"
        assert EXPANSION_LEVEL_NAMES["deep"] == "深度扩写"

    def test_get_expansion_multiplier(self):
        """测试获取扩写倍数方法"""
        assert ExpansionAIService.get_expansion_multiplier("light") == 1.5
        assert ExpansionAIService.get_expansion_multiplier("medium") == 2.0
        assert ExpansionAIService.get_expansion_multiplier("deep") == 3.0
        # 未知级别返回默认值
        assert ExpansionAIService.get_expansion_multiplier("unknown") == 2.0

    def test_get_expansion_level_name(self):
        """测试获取扩写级别名称方法"""
        assert ExpansionAIService.get_expansion_level_name("light") == "轻度扩写"
        assert ExpansionAIService.get_expansion_level_name("medium") == "中度扩写"
        assert ExpansionAIService.get_expansion_level_name("deep") == "深度扩写"
        # 未知级别返回原值
        assert ExpansionAIService.get_expansion_level_name("unknown") == "unknown"


class TestExpansionAIServiceInit:
    """测试服务初始化"""

    def test_default_provider(self):
        """测试默认 provider"""
        service = ExpansionAIService()
        assert service.provider == "openai"

    def test_custom_provider(self):
        """测试自定义 provider"""
        service = ExpansionAIService({"provider": "anthropic"})
        assert service.provider == "anthropic"

    def test_custom_model(self):
        """测试自定义 model"""
        service = ExpansionAIService({"model": "gpt-4"})
        assert service.model == "gpt-4"

    def test_custom_temperature(self):
        """测试自定义 temperature"""
        service = ExpansionAIService({
            "prompt_config": {"temperature": 0.5}
        })
        assert service.temperature == 0.5

    def test_default_temperature(self):
        """测试默认 temperature"""
        service = ExpansionAIService()
        assert service.temperature == 0.7

    def test_custom_max_tokens(self):
        """测试自定义 max_tokens"""
        service = ExpansionAIService({
            "prompt_config": {"max_tokens": 2000}
        })
        assert service.max_tokens == 2000


class TestFormatStyleRequirements:
    """测试文风要求格式化"""

    def test_empty_style(self):
        """测试空文风画像"""
        service = ExpansionAIService()
        result = service._format_style_requirements({})
        assert result == "保持原文风格"

    def test_none_style(self):
        """测试 None 文风画像"""
        service = ExpansionAIService()
        result = service._format_style_requirements(None)
        assert result == "保持原文风格"

    def test_full_style(self):
        """测试完整文风画像"""
        service = ExpansionAIService()
        result = service._format_style_requirements({
            "narrative_pov": "第三人称",
            "tone": "轻松幽默",
            "sentence_style": "短句为主",
            "vocabulary": "口语化",
            "rhythm": "快节奏",
            "notable_features": "善用比喻",
        })
        assert "叙事视角：第三人称" in result
        assert "基调氛围：轻松幽默" in result
        assert "句式风格：短句为主" in result

    def test_partial_style(self):
        """测试部分文风画像"""
        service = ExpansionAIService()
        result = service._format_style_requirements({
            "narrative_pov": "第一人称",
            "tone": "沉稳内敛",
        })
        assert "叙事视角：第一人称" in result
        assert "基调氛围：沉稳内敛" in result
        assert "句式风格" not in result