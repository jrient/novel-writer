"""
AI 相关请求/响应 Schema
"""
from typing import Optional, List, Dict, Literal
from pydantic import BaseModel, Field


VALID_ACTIONS = Literal[
    "continue", "rewrite", "expand", "outline",
    "character_analysis", "analyze_expand", "free_chat", "revise", "polish_character",
    "plot_enhance", "generate_title"
]


class PinnedContext(BaseModel):
    """用户固定的上下文实体"""
    characters: List[int] = Field(default_factory=list, description="固定的角色 ID 列表")
    worldbuilding: List[int] = Field(default_factory=list, description="固定的世界观 ID 列表")
    events: List[int] = Field(default_factory=list, description="固定的事件 ID 列表")
    notes: List[int] = Field(default_factory=list, description="固定的笔记 ID 列表")


class ContextEntity(BaseModel):
    """上下文实体（带匹配信息）"""
    id: int
    type: str = Field(description="实体类型: character/worldbuilding/event/note/outline")
    name: str = Field(description="实体名称/标题")
    summary: str = Field(default="", description="简要描述")
    relevance: float = Field(default=0, description="相关性分数 0-1")
    match_reason: str = Field(default="", description="匹配理由")
    is_pinned: bool = Field(default=False, description="是否为用户固定")


class AIGenerateRequest(BaseModel):
    """AI 生成请求"""
    action: VALID_ACTIONS = Field(
        ...,
        description="操作类型: continue(续写), rewrite(改写), expand(扩写), outline(大纲), character_analysis(角色分析), analyze_expand(开篇分析), free_chat(自由对话), revise(意见修改), plot_enhance(剧情完善)"
    )
    content: str = Field(default="", max_length=50000, description="当前内容文本")
    provider: Optional[str] = Field(default=None, description="AI 提供商: openai/anthropic/ollama")
    title: Optional[str] = Field(default="", max_length=200, description="项目标题（大纲生成用）")
    genre: Optional[str] = Field(default="", max_length=50, description="项目类型（大纲生成用）")
    description: Optional[str] = Field(default="", max_length=2000, description="项目简介（大纲生成用）")
    question: Optional[str] = Field(default="", max_length=2000, description="用户问题（自由对话用）")
    chapter_id: Optional[int] = Field(default=None, description="当前章节 ID")
    pinned_context: Optional[PinnedContext] = Field(default=None, description="用户固定的上下文实体")


class ContextPreviewResponse(BaseModel):
    """上下文预览响应"""
    entities: List[ContextEntity] = Field(default_factory=list, description="匹配到的实体列表")
    suggestions: str = Field(default="", description="AI 建议")


class BatchGenerateRequest(BaseModel):
    """AI 批量生成请求"""
    chapter_count: int = Field(default=5, ge=1, le=30, description="生成章节数")
    words_per_chapter: int = Field(default=1500, ge=500, le=5000, description="每章字数")
    reference_ids: List[int] = Field(default_factory=list, description="参考小说 ID 列表")
    use_knowledge: bool = Field(default=True, description="是否使用知识库")
    remove_ai_traces: bool = Field(default=True, description="是否在每章生成后进行 AI 除痕处理")


class AIConfigResponse(BaseModel):
    """AI 配置信息响应"""
    default_provider: str
    available_providers: List[str]
    models: Dict[str, str]
