"""
剧本 Schema 测试
"""
import pytest
from pydantic import ValidationError

from app.schemas.drama import (
    AIPromptConfig,
    AIConfig,
    ScriptProjectCreate,
    ScriptProjectUpdate,
    ScriptProjectResponse,
    ScriptNodeCreate,
    ScriptNodeUpdate,
    ScriptNodeResponse,
    ScriptNodeTreeResponse,
    ReorderRequest,
    SessionAnswerRequest,
    ScriptSessionResponse,
    ExpandNodeRequest,
    RewriteRequest,
    GlobalDirectiveRequest,
    EXPLANATORY_NODE_TYPES,
    DYNAMIC_NODE_TYPES,
)
from datetime import datetime


# ---------------------------------------------------------------------------
# AIConfig 测试
# ---------------------------------------------------------------------------

def test_ai_prompt_config_valid():
    cfg = AIPromptConfig(system_prompt="你是专业编剧", temperature=0.8, max_tokens=2000)
    assert cfg.temperature == 0.8
    assert cfg.max_tokens == 2000


def test_ai_prompt_config_temperature_bounds():
    with pytest.raises(ValidationError):
        AIPromptConfig(temperature=3.0)
    with pytest.raises(ValidationError):
        AIPromptConfig(temperature=-0.1)


def test_ai_config_valid():
    cfg = AIConfig(provider="openai", model="gpt-4")
    assert cfg.provider == "openai"
    assert cfg.model == "gpt-4"
    assert cfg.prompt_config is None


def test_ai_config_empty():
    cfg = AIConfig()
    assert cfg.provider is None
    assert cfg.model is None


# ---------------------------------------------------------------------------
# ScriptProjectCreate 测试
# ---------------------------------------------------------------------------

def test_project_create_valid_dynamic():
    data = ScriptProjectCreate(title="动态剧本", script_type="dynamic")
    assert data.title == "动态剧本"
    assert data.script_type == "dynamic"
    assert data.concept is None


def test_project_create_valid_explanatory():
    data = ScriptProjectCreate(title="说明剧本", script_type="explanatory", concept="量子物理科普")
    assert data.script_type == "explanatory"
    assert data.concept == "量子物理科普"


def test_project_create_invalid_type():
    with pytest.raises(ValidationError):
        ScriptProjectCreate(title="错误类型", script_type="unknown")


def test_project_create_empty_title():
    with pytest.raises(ValidationError):
        ScriptProjectCreate(title="", script_type="dynamic")


def test_project_create_with_metadata():
    data = ScriptProjectCreate(
        title="带元数据",
        script_type="dynamic",
        **{"metadata": {"tags": ["科幻"]}}
    )
    assert data.metadata_ == {"tags": ["科幻"]}


def test_project_create_with_ai_config():
    data = ScriptProjectCreate(
        title="带AI配置",
        script_type="dynamic",
        ai_config=AIConfig(provider="openai", model="gpt-4"),
    )
    assert data.ai_config.provider == "openai"


# ---------------------------------------------------------------------------
# ScriptProjectUpdate 测试
# ---------------------------------------------------------------------------

def test_project_update_partial():
    data = ScriptProjectUpdate(title="新标题")
    assert data.title == "新标题"
    assert data.status is None
    assert data.concept is None


def test_project_update_status():
    for status in ["drafting", "outlined", "writing", "completed"]:
        data = ScriptProjectUpdate(status=status)
        assert data.status == status


def test_project_update_invalid_status():
    with pytest.raises(ValidationError):
        ScriptProjectUpdate(status="invalid_status")


def test_project_update_empty():
    data = ScriptProjectUpdate()
    assert data.title is None
    assert data.status is None


# ---------------------------------------------------------------------------
# ScriptProjectResponse 测试
# ---------------------------------------------------------------------------

def test_project_response_from_attributes():
    now = datetime.now()

    class FakeProject:
        id = 1
        user_id = 2
        title = "测试"
        script_type = "dynamic"
        concept = "概念"
        status = "drafting"
        ai_config = None
        metadata_ = None
        created_at = now
        updated_at = None

    resp = ScriptProjectResponse.model_validate(FakeProject())
    assert resp.id == 1
    assert resp.title == "测试"
    assert resp.user_id == 2


# ---------------------------------------------------------------------------
# ScriptNodeCreate 测试
# ---------------------------------------------------------------------------

def test_node_create_valid():
    data = ScriptNodeCreate(project_id=1, node_type="dialogue", speaker="主角", content="你好")
    assert data.node_type == "dialogue"
    assert data.speaker == "主角"
    assert data.sort_order == 0


def test_node_create_all_valid_types():
    all_types = list(DYNAMIC_NODE_TYPES) + list(EXPLANATORY_NODE_TYPES)
    for nt in all_types:
        data = ScriptNodeCreate(project_id=1, node_type=nt)
        assert data.node_type == nt


def test_node_create_invalid_type():
    with pytest.raises(ValidationError):
        ScriptNodeCreate(project_id=1, node_type="unknown_type")


def test_node_create_with_parent():
    data = ScriptNodeCreate(project_id=1, node_type="scene", parent_id=5)
    assert data.parent_id == 5


# ---------------------------------------------------------------------------
# ScriptNodeUpdate 测试
# ---------------------------------------------------------------------------

def test_node_update_partial():
    data = ScriptNodeUpdate(content="新内容", is_completed=True)
    assert data.content == "新内容"
    assert data.is_completed is True
    assert data.title is None


def test_node_update_empty():
    data = ScriptNodeUpdate()
    assert data.title is None
    assert data.content is None
    assert data.is_completed is None


# ---------------------------------------------------------------------------
# ScriptNodeResponse 测试
# ---------------------------------------------------------------------------

def test_node_response_from_attributes():
    now = datetime.now()

    class FakeNode:
        id = 10
        project_id = 1
        parent_id = None
        node_type = "episode"
        title = "第一集"
        content = "内容"
        speaker = None
        visual_desc = None
        sort_order = 0
        is_completed = False
        metadata_ = None
        created_at = now
        updated_at = None

    resp = ScriptNodeResponse.model_validate(FakeNode())
    assert resp.id == 10
    assert resp.node_type == "episode"
    assert resp.is_completed is False


# ---------------------------------------------------------------------------
# ScriptNodeTreeResponse 测试
# ---------------------------------------------------------------------------

def test_tree_response_with_children():
    now = datetime.now()
    child_data = {
        "id": 2, "project_id": 1, "parent_id": 1, "node_type": "scene",
        "title": "场景1", "content": None, "speaker": None, "visual_desc": None,
        "sort_order": 0, "is_completed": False, "metadata": None,
        "created_at": now, "updated_at": None, "children": [],
    }
    parent_data = {
        "id": 1, "project_id": 1, "parent_id": None, "node_type": "episode",
        "title": "第一集", "content": None, "speaker": None, "visual_desc": None,
        "sort_order": 0, "is_completed": False, "metadata": None,
        "created_at": now, "updated_at": None, "children": [child_data],
    }
    tree = ScriptNodeTreeResponse(**parent_data)
    assert len(tree.children) == 1
    assert tree.children[0].node_type == "scene"


# ---------------------------------------------------------------------------
# ReorderRequest 测试
# ---------------------------------------------------------------------------

def test_reorder_request_valid():
    data = ReorderRequest(node_ids=[3, 1, 2])
    assert data.node_ids == [3, 1, 2]


def test_reorder_request_empty_list():
    data = ReorderRequest(node_ids=[])
    assert data.node_ids == []


# ---------------------------------------------------------------------------
# SessionAnswerRequest 测试
# ---------------------------------------------------------------------------

def test_session_answer_valid():
    data = SessionAnswerRequest(answer="这是我的回答")
    assert data.answer == "这是我的回答"


def test_session_answer_empty():
    with pytest.raises(ValidationError):
        SessionAnswerRequest(answer="")


# ---------------------------------------------------------------------------
# ScriptSessionResponse 测试
# ---------------------------------------------------------------------------

def test_session_response_from_attributes():
    now = datetime.now()

    class FakeSession:
        id = 5
        project_id = 1
        state = "collecting"
        history = [{"role": "user", "content": "hi"}]
        outline_draft = None
        current_node_id = None
        created_at = now
        updated_at = None

    resp = ScriptSessionResponse.model_validate(FakeSession())
    assert resp.id == 5
    assert resp.state == "collecting"
    assert len(resp.history) == 1


# ---------------------------------------------------------------------------
# AI 操作请求测试
# ---------------------------------------------------------------------------

def test_expand_node_request():
    data = ExpandNodeRequest(node_id=1, instructions="请展开这一集")
    assert data.node_id == 1
    assert data.instructions == "请展开这一集"


def test_expand_node_without_instructions():
    data = ExpandNodeRequest(node_id=1)
    assert data.instructions is None


def test_rewrite_request_valid():
    data = RewriteRequest(node_id=2, instructions="改写为更有张力的风格")
    assert data.node_id == 2
    assert data.instructions == "改写为更有张力的风格"


def test_rewrite_request_empty_instructions():
    with pytest.raises(ValidationError):
        RewriteRequest(node_id=2, instructions="")


def test_global_directive_valid():
    data = GlobalDirectiveRequest(directive="整体风格调整为轻松幽默")
    assert data.directive == "整体风格调整为轻松幽默"


def test_global_directive_empty():
    with pytest.raises(ValidationError):
        GlobalDirectiveRequest(directive="")


# ---------------------------------------------------------------------------
# 常量集合测试
# ---------------------------------------------------------------------------

def test_explanatory_node_types():
    assert EXPLANATORY_NODE_TYPES == {"intro", "section", "narration"}


def test_dynamic_node_types():
    assert DYNAMIC_NODE_TYPES == {"episode", "scene", "dialogue", "action", "effect", "inner_voice"}


def test_node_types_are_disjoint():
    assert EXPLANATORY_NODE_TYPES.isdisjoint(DYNAMIC_NODE_TYPES)
