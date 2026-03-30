"""
剧本生成模块 Pydantic Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# --- 类型常量 ---

VALID_SCRIPT_TYPES = Literal["explanatory", "dynamic"]

VALID_NODE_TYPES = Literal[
    "episode", "scene", "dialogue", "action", "effect",
    "inner_voice", "section", "narration", "intro"
]

EXPLANATORY_NODE_TYPES = {"intro", "section", "narration"}
DYNAMIC_NODE_TYPES = {"episode", "scene", "dialogue", "action", "effect", "inner_voice"}


# --- AI 配置 ---

class AIPromptConfig(BaseModel):
    """AI 提示词配置"""
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大输出 token 数")


class AIConfig(BaseModel):
    """AI 配置"""
    provider: Optional[str] = Field(None, description="AI 提供商")
    model: Optional[str] = Field(None, description="模型名称")
    prompt_config: Optional[AIPromptConfig] = Field(None, description="提示词配置")


# --- ScriptProject Schemas ---

class ScriptProjectCreate(BaseModel):
    """创建剧本项目请求"""
    title: str = Field(..., min_length=1, max_length=200, description="剧本标题")
    script_type: VALID_SCRIPT_TYPES = Field(..., description="剧本类型: explanatory/dynamic")
    concept: Optional[str] = Field(None, description="创意概念")
    ai_config: Optional[AIConfig] = Field(None, description="AI配置")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)


class ScriptProjectUpdate(BaseModel):
    """更新剧本项目请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="剧本标题")
    concept: Optional[str] = Field(None, description="创意概念")
    status: Optional[Literal["drafting", "outlined", "writing", "completed"]] = Field(
        None, description="状态"
    )
    ai_config: Optional[AIConfig] = Field(None, description="AI配置")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)


class ScriptProjectResponse(BaseModel):
    """剧本项目响应"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int
    title: str
    script_type: str
    concept: Optional[str] = None
    status: str
    ai_config: Optional[Dict[str, Any]] = None
    metadata_: Optional[Dict[str, Any]] = Field(None, serialization_alias="metadata")
    created_at: datetime
    updated_at: Optional[datetime] = None


class ScriptProjectListResponse(BaseModel):
    """剧本项目列表响应"""
    items: List[ScriptProjectResponse]
    total: int
    page: int
    page_size: int


# --- ScriptNode Schemas ---

class ScriptNodeCreate(BaseModel):
    """创建剧本节点请求"""
    parent_id: Optional[int] = Field(None, description="父节点ID")
    node_type: VALID_NODE_TYPES = Field(..., description="节点类型")
    title: Optional[str] = Field(None, max_length=200, description="标题")
    content: Optional[str] = Field(None, description="内容")
    speaker: Optional[str] = Field(None, max_length=100, description="说话者")
    visual_desc: Optional[str] = Field(None, description="视觉描述")
    sort_order: int = Field(0, description="排序")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)


class ScriptNodeUpdate(BaseModel):
    """更新剧本节点请求"""
    title: Optional[str] = Field(None, max_length=200, description="标题")
    content: Optional[str] = Field(None, description="内容")
    speaker: Optional[str] = Field(None, max_length=100, description="说话者")
    visual_desc: Optional[str] = Field(None, description="视觉描述")
    sort_order: Optional[int] = Field(None, description="排序")
    is_completed: Optional[bool] = Field(None, description="是否完成")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)


class ScriptNodeResponse(BaseModel):
    """剧本节点响应"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    project_id: int
    parent_id: Optional[int] = None
    node_type: str
    title: Optional[str] = None
    content: Optional[str] = None
    speaker: Optional[str] = None
    visual_desc: Optional[str] = None
    sort_order: int
    is_completed: bool
    metadata_: Optional[Dict[str, Any]] = Field(None, serialization_alias="metadata")
    created_at: datetime
    updated_at: Optional[datetime] = None


class ScriptNodeTreeResponse(ScriptNodeResponse):
    """剧本节点树形响应（含子节点）"""
    children: List["ScriptNodeTreeResponse"] = []


ScriptNodeTreeResponse.model_rebuild()


class ReorderRequest(BaseModel):
    """节点重排序请求"""
    node_ids: List[int] = Field(..., description="按新顺序排列的节点ID列表")


# --- ScriptSession Schemas ---

class SessionAnswerRequest(BaseModel):
    """会话回答请求"""
    answer: str = Field(..., min_length=1, description="用户回答")


class ScriptSessionResponse(BaseModel):
    """剧本会话响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    state: str
    history: Optional[List[Any]] = None
    outline_draft: Optional[Dict[str, Any]] = None
    current_node_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class SessionSummaryResponse(BaseModel):
    """会话摘要响应（中文键名）"""
    故事概要: str
    主要角色: List[str]
    核心冲突: str
    场景设定: str
    风格基调: str


# --- AI 操作请求 ---

class ExpandNodeRequest(BaseModel):
    """展开节点请求"""
    node_id: Optional[int] = Field(None, description="要展开的节点ID")
    instructions: Optional[str] = Field(None, description="额外指令")


class RewriteRequest(BaseModel):
    """重写请求"""
    node_id: int = Field(..., description="要重写的节点ID")
    instructions: str = Field(..., min_length=1, description="重写指令")


class GlobalDirectiveRequest(BaseModel):
    """全局指令请求"""
    directive: str = Field(..., min_length=1, description="全局指令内容")
