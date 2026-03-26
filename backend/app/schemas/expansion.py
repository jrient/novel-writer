"""
扩写模块 Pydantic Schemas
"""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# --- 类型常量 ---

VALID_EXPANSION_LEVELS = Literal["light", "medium", "deep"]

VALID_SOURCE_TYPES = Literal["upload", "novel", "drama", "manual"]

VALID_PROJECT_STATUSES = Literal[
    "created", "analyzed", "segmented", "expanding", "paused", "error", "completed"
]

VALID_SEGMENT_STATUSES = Literal["pending", "expanding", "completed", "error", "skipped"]

VALID_EXECUTION_MODES = Literal["auto", "step_by_step"]

VALID_CONVERT_TARGETS = Literal["novel", "drama"]


# --- 文风画像 ---

class StyleProfile(BaseModel):
    """文风画像"""
    narrative_pov: Optional[str] = Field(None, description="叙事视角")
    tone: Optional[str] = Field(None, description="基调/氛围")
    sentence_style: Optional[str] = Field(None, description="句式风格")
    vocabulary: Optional[str] = Field(None, description="词汇特点")
    rhythm: Optional[str] = Field(None, description="节奏特点")
    notable_features: Optional[str] = Field(None, description="显著特征")


# --- AI 配置（复用 drama 模式）---

class ExpansionAIPromptConfig(BaseModel):
    """AI 提示词配置"""
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="温度参数")
    max_tokens: Optional[int] = Field(None, gt=0, description="最大输出 token 数")


class ExpansionAIConfig(BaseModel):
    """AI 配置"""
    provider: Optional[str] = Field(None, description="AI 提供商")
    model: Optional[str] = Field(None, description="模型名称")
    prompt_config: Optional[ExpansionAIPromptConfig] = Field(None, description="提示词配置")


# --- ExpansionProject Schemas ---

class ExpansionProjectCreate(BaseModel):
    """创建扩写项目请求"""
    title: str = Field(..., min_length=1, max_length=200, description="项目标题")
    source_type: VALID_SOURCE_TYPES = Field(..., description="来源类型: upload/novel/drama/manual")
    original_text: str = Field(..., max_length=30000, description="原始文本，最多30000字")
    source_ref: Optional[Dict[str, Any]] = Field(None, description="来源引用")
    expansion_level: VALID_EXPANSION_LEVELS = Field("medium", description="扩写深度")
    target_word_count: Optional[int] = Field(None, gt=0, description="目标字数")
    style_instructions: Optional[str] = Field(None, description="文风调整指令")
    ai_config: Optional[ExpansionAIConfig] = Field(None, description="AI配置")
    execution_mode: VALID_EXECUTION_MODES = Field("auto", description="执行模式")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)

    @field_validator("original_text")
    @classmethod
    def validate_text_length(cls, v: str) -> str:
        if len(v) > 30000:
            raise ValueError("原文超过30000字限制")
        return v


class ExpansionProjectUpdate(BaseModel):
    """更新扩写项目请求"""
    title: Optional[str] = Field(None, min_length=1, max_length=200, description="项目标题")
    expansion_level: Optional[VALID_EXPANSION_LEVELS] = Field(None, description="扩写深度")
    target_word_count: Optional[int] = Field(None, gt=0, description="目标字数")
    style_instructions: Optional[str] = Field(None, description="文风调整指令")
    status: Optional[VALID_PROJECT_STATUSES] = Field(None, description="状态")
    execution_mode: Optional[VALID_EXECUTION_MODES] = Field(None, description="执行模式")
    ai_config: Optional[ExpansionAIConfig] = Field(None, description="AI配置")
    metadata_: Optional[Dict[str, Any]] = Field(None, alias="metadata", description="元数据")

    model_config = ConfigDict(populate_by_name=True)


class ExpansionProjectResponse(BaseModel):
    """扩写项目响应"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: int
    user_id: int
    title: str
    source_type: str
    source_ref: Optional[Dict[str, Any]] = None
    original_text: Optional[str] = None
    word_count: int
    summary: Optional[str] = None
    style_profile: Optional[Dict[str, Any]] = None
    expansion_level: str
    target_word_count: Optional[int] = None
    style_instructions: Optional[str] = None
    ai_config: Optional[Dict[str, Any]] = None
    status: str
    execution_mode: str
    version: int
    metadata_: Optional[Dict[str, Any]] = Field(
        None,
        serialization_alias="metadata",
        description="元数据"
    )
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExpansionProjectListResponse(BaseModel):
    """扩写项目列表响应（不含original_text）"""
    items: List["ExpansionProjectListItem"]
    total: int
    page: int
    page_size: int


class ExpansionProjectListItem(BaseModel):
    """扩写项目列表项"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    source_type: str
    word_count: int
    status: str
    expansion_level: str
    created_at: datetime
    updated_at: Optional[datetime] = None


# --- ExpansionSegment Schemas ---

class ExpansionSegmentResponse(BaseModel):
    """扩写分段响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    sort_order: int
    title: Optional[str] = None
    original_content: str
    expanded_content: Optional[str] = None
    expansion_level: Optional[str] = None
    custom_instructions: Optional[str] = None
    status: str
    error_message: Optional[str] = None
    original_word_count: int
    expanded_word_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ExpansionSegmentUpdate(BaseModel):
    """更新扩写分段请求"""
    title: Optional[str] = Field(None, max_length=200, description="段落标题")
    expansion_level: Optional[VALID_EXPANSION_LEVELS] = Field(None, description="扩写深度")
    custom_instructions: Optional[str] = Field(None, description="特殊扩写指令")

    model_config = ConfigDict(populate_by_name=True)


# --- 分段操作请求 ---

class SegmentSplitRequest(BaseModel):
    """分段拆分请求"""
    segment_id: int = Field(..., description="要拆分的分段ID")
    split_position: int = Field(..., ge=0, description="拆分位置（字符索引）")


class SegmentMergeRequest(BaseModel):
    """分段合并请求"""
    segment_ids: List[int] = Field(..., min_length=2, description="要合并的分段ID列表")

    @field_validator("segment_ids")
    @classmethod
    def validate_segment_ids(cls, v: List[int]) -> List[int]:
        if len(v) < 2:
            raise ValueError("至少需要2个分段才能合并")
        return v


class SegmentReorderRequest(BaseModel):
    """分段重排序请求"""
    segment_ids: List[int] = Field(..., description="按新顺序排列的分段ID列表")


# --- 导入请求 ---

class ImportFromNovelRequest(BaseModel):
    """从小说导入请求"""
    title: str = Field(..., min_length=1, max_length=200, description="项目标题")
    project_id: int = Field(..., description="小说项目ID")
    chapter_ids: Optional[List[int]] = Field(None, description="章节ID列表，不指定则导入全部")
    expansion_level: VALID_EXPANSION_LEVELS = Field("medium", description="扩写深度")
    ai_config: Optional[ExpansionAIConfig] = Field(None, description="AI配置")
    execution_mode: VALID_EXECUTION_MODES = Field("auto", description="执行模式")


class ImportFromDramaRequest(BaseModel):
    """从剧本导入请求"""
    title: str = Field(..., min_length=1, max_length=200, description="项目标题")
    project_id: int = Field(..., description="剧本项目ID")
    expansion_level: VALID_EXPANSION_LEVELS = Field("medium", description="扩写深度")
    ai_config: Optional[ExpansionAIConfig] = Field(None, description="AI配置")
    execution_mode: VALID_EXECUTION_MODES = Field("auto", description="执行模式")


# --- 转换请求 ---

class ConvertRequest(BaseModel):
    """转换请求"""
    target: VALID_CONVERT_TARGETS = Field(..., description="目标类型: novel/drama")


# --- 扩写操作请求 ---

class ExpandSegmentRequest(BaseModel):
    """单段扩写请求"""
    segment_id: int = Field(..., description="要扩写的分段ID")
    instructions: Optional[str] = Field(None, description="额外指令")