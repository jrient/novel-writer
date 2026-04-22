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


def test_generate_episode_content_method_exists():
    """generate_episode_content 方法存在"""
    import inspect
    sig = inspect.signature(ScriptAIService.generate_episode_content)
    assert "episode_index" in sig.parameters
    assert "total_episodes" in sig.parameters
    assert "current_episode" in sig.parameters


def test_generate_episode_content_prompt_has_required_placeholders():
    """动态漫 episode_content prompt 包含必要占位符"""
    from app.services.script_ai_service import DYNAMIC_PROMPTS
    user_prompt = DYNAMIC_PROMPTS["episode_content"]["user"]
    system_prompt = DYNAMIC_PROMPTS["episode_content"]["system"]
    for placeholder in ["{title}", "{outline_summary}", "{current_episode}",
                        "{episode_position}", "{main_characters}", "{core_conflict}"]:
        assert placeholder in user_prompt, f"Missing placeholder: {placeholder}"
    # 确保 prompt 要求输出纯文本而非 JSON
    assert "不输出 JSON" in system_prompt
    assert "800-1500 字" in user_prompt


def test_explanatory_episode_content_prompt_exists():
    """解说漫 episode_content prompt 符合专业剧本格式：场景/画面/对白/旁白四要素齐全"""
    from app.services.script_ai_service import EXPLANATORY_PROMPTS
    assert "episode_content" in EXPLANATORY_PROMPTS
    user_prompt = EXPLANATORY_PROMPTS["episode_content"]["user"]
    # 必备占位符
    for placeholder in ["{title}", "{outline_summary}", "{episode_number}",
                        "{episode_position}", "{style_tone}",
                        "{main_characters}", "{core_conflict}"]:
        assert placeholder in user_prompt, f"Missing placeholder: {placeholder}"
    # 剧本四要素必须都被要求
    assert "对白" in user_prompt
    assert "△" in user_prompt  # 动作标记
    # 必须包含场景标记格式
    assert "{episode_number}-1" in user_prompt
    # 必须包含开局爆点要求
    assert "爆点" in user_prompt or "第一镜" in user_prompt
    # 必须限制对白长度和情感层次
    assert "10-30字" in user_prompt or "情感" in user_prompt


def test_generate_episode_content_accepts_script_type():
    """generate_episode_content 接受 script_type 参数"""
    import inspect
    sig = inspect.signature(ScriptAIService.generate_episode_content)
    assert "script_type" in sig.parameters


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


def test_build_settings_context_empty():
    """空 settings 返回空字符串"""
    svc = ScriptAIService(ai_config={}, project_settings={})
    assert svc._build_settings_context() == ""


def test_build_settings_context_full():
    """非空 settings 返回正确格式的上下文字符串"""
    settings_data = {
        "characters": [
            {"id": "c1", "name": "张三", "description": "豪爽"},
            {"id": "c2", "name": "李四", "description": ""},  # 空描述不追加冒号
        ],
        "world_setting": "架空古代",
        "tone": "热血",
        "plot_anchors": "主角不能死",
        "persistent_directive": "不要出现现代词汇",
    }
    svc = ScriptAIService(ai_config={}, project_settings=settings_data)
    ctx = svc._build_settings_context()
    assert "【剧本设定】" in ctx
    assert "张三：豪爽" in ctx
    assert "李四" in ctx
    assert "架空古代" in ctx
    assert "热血" in ctx
    assert "主角不能死" in ctx
    assert "不要出现现代词汇" in ctx


def test_build_settings_context_partial():
    """只填了部分字段，不注入空字段"""
    svc = ScriptAIService(ai_config={}, project_settings={"tone": "悬疑"})
    ctx = svc._build_settings_context()
    assert "悬疑" in ctx
    assert "世界观" not in ctx
    assert "人物" not in ctx


def test_settings_prepended_to_system_prompt():
    """project_settings 内容出现在 system prompt 的最前面"""
    svc = ScriptAIService(
        ai_config={},
        project_settings={"persistent_directive": "保持角色一致性"},
    )
    system = svc._get_system_prompt("question", "dynamic")
    assert system is not None
    assert system.startswith("【剧本设定】")
    assert "保持角色一致性" in system


def test_empty_settings_does_not_modify_system_prompt():
    """空 settings 不影响原有 system prompt"""
    svc_with = ScriptAIService(ai_config={}, project_settings={})
    svc_without = ScriptAIService(ai_config={})
    assert svc_with._get_system_prompt("question", "dynamic") == \
           svc_without._get_system_prompt("question", "dynamic")
