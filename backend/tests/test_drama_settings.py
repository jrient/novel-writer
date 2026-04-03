# backend/tests/test_drama_settings.py
"""
剧本设定 Schema 单元测试
测试 ProjectSettingsUpdate 的字段验证
"""
import pytest
from pydantic import ValidationError


def test_project_settings_valid():
    """有效的 settings 通过验证"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    s = ProjectSettingsUpdate(
        characters=[CharacterSettingItem(id="c1", name="张三", description="豪爽")],
        world_setting="架空古代",
        tone="热血",
        plot_anchors="主角不能死",
        persistent_directive="不要出现现代词汇",
    )
    assert s.tone == "热血"
    assert s.characters[0].name == "张三"


def test_project_settings_defaults():
    """所有字段均有默认值"""
    from app.routers.drama import ProjectSettingsUpdate
    s = ProjectSettingsUpdate()
    assert s.characters == []
    assert s.world_setting == ""
    assert s.tone == ""
    assert s.plot_anchors == ""
    assert s.persistent_directive == ""


def test_character_name_max_length():
    """角色名称超过 100 字符时验证失败"""
    from app.routers.drama import CharacterSettingItem
    with pytest.raises(ValidationError):
        CharacterSettingItem(id="c1", name="x" * 101, description="")


def test_character_description_max_length():
    """角色描述超过 2000 字符时验证失败"""
    from app.routers.drama import CharacterSettingItem
    with pytest.raises(ValidationError):
        CharacterSettingItem(id="c1", name="张三", description="x" * 2001)


def test_tone_max_length():
    """tone 超过 1000 字符时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(tone="x" * 1001)


def test_world_setting_max_length():
    """world_setting 超过 3000 字符时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(world_setting="x" * 3001)


def test_characters_max_count():
    """角色列表超过 50 个时验证失败"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    chars = [CharacterSettingItem(id=f"c{i}", name=f"角色{i}", description="") for i in range(51)]
    with pytest.raises(ValidationError):
        ProjectSettingsUpdate(characters=chars)


def test_model_dump_roundtrip():
    """model_dump 后可以重新构造"""
    from app.routers.drama import ProjectSettingsUpdate, CharacterSettingItem
    s = ProjectSettingsUpdate(
        characters=[CharacterSettingItem(id="c1", name="张三", description="豪爽")],
        tone="热血",
    )
    d = s.model_dump()
    s2 = ProjectSettingsUpdate(**d)
    assert s2.tone == "热血"
    assert s2.characters[0].name == "张三"