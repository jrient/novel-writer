"""
script_ai_service 单元测试
"""
import pytest
from app.services.script_ai_service import DYNAMIC_PROMPTS, ScriptAIService


def test_dynamic_outline_prompt_has_episode_count_placeholder():
    """动态漫 outline prompt 包含 {episode_count} 占位符"""
    user_prompt = DYNAMIC_PROMPTS["outline"]["user"]
    assert "{episode_count}" in user_prompt


def test_dynamic_outline_prompt_no_scene_content():
    """动态漫 outline prompt 不再要求生成 scene 内容"""
    user_prompt = DYNAMIC_PROMPTS["outline"]["user"]
    # 新 prompt 只要求标题+概要，不要求 scene content
    assert "场景描述" not in user_prompt
    assert "对白" not in user_prompt


def test_expand_episode_prompt_exists():
    """expand_episode prompt 存在"""
    assert "expand_episode" in DYNAMIC_PROMPTS


def test_expand_episode_prompt_has_required_placeholders():
    """expand_episode prompt 包含必要占位符"""
    user_prompt = DYNAMIC_PROMPTS["expand_episode"]["user"]
    for placeholder in ["{title}", "{outline_summary}", "{current_episode}",
                        "{episode_position}", "{main_characters}", "{core_conflict}"]:
        assert placeholder in user_prompt, f"Missing placeholder: {placeholder}"


def test_calc_max_tokens_for_episode_count():
    """max_tokens 根据集数动态计算"""
    from app.services.script_ai_service import calc_outline_max_tokens
    assert calc_outline_max_tokens(20) == 8000
    assert calc_outline_max_tokens(60) == max(8000, 60 * 150)  # 9000
    assert calc_outline_max_tokens(250) == 32000   # capped


def test_generate_outline_accepts_episode_count():
    """generate_outline 接受 episode_count 参数"""
    import inspect
    sig = inspect.signature(ScriptAIService.generate_outline)
    assert "episode_count" in sig.parameters
