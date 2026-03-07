"""
AI 相关请求/响应 Schema
"""
from typing import Optional, List, Dict
from pydantic import BaseModel, Field


class AIGenerateRequest(BaseModel):
    """AI 生成请求"""
    action: str = Field(
        ...,
        description="操作类型: continue(续写), rewrite(改写), expand(扩写), outline(大纲), character_analysis(角色分析), free_chat(自由对话)"
    )
    content: str = Field(default="", description="当前内容文本")
    provider: Optional[str] = Field(default=None, description="AI 提供商: openai/anthropic/ollama")
    title: Optional[str] = Field(default="", description="项目标题（大纲生成用）")
    genre: Optional[str] = Field(default="", description="项目类型（大纲生成用）")
    description: Optional[str] = Field(default="", description="项目简介（大纲生成用）")
    question: Optional[str] = Field(default="", description="用户问题（自由对话用）")
    chapter_id: Optional[int] = Field(default=None, description="当前章节 ID")


class BatchGenerateRequest(BaseModel):
    """AI 批量生成请求"""
    chapter_count: int = Field(default=5, ge=1, le=30, description="生成章节数")
    words_per_chapter: int = Field(default=1500, ge=500, le=5000, description="每章字数")
    reference_ids: List[int] = Field(default_factory=list, description="参考小说 ID 列表")
    use_knowledge: bool = Field(default=True, description="是否使用知识库")


class AIConfigResponse(BaseModel):
    """AI 配置信息响应"""
    default_provider: str
    available_providers: List[str]
    models: Dict[str, str]
