from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class CanonEntityOut(BaseModel):
    id: int
    reference_id: int
    entity_type: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    importance: str
    confidence: float
    review_status: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class CanonEntityCreate(BaseModel):
    entity_type: str
    canonical_name: str
    aliases: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    attributes: Dict[str, Any] = Field(default_factory=dict)
    source_refs: List[Dict[str, Any]] = Field(default_factory=list)
    importance: str = "major"


class CanonEntityUpdate(BaseModel):
    canonical_name: Optional[str] = None
    aliases: Optional[List[str]] = None
    summary: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    importance: Optional[str] = None
    review_status: Optional[str] = None


class CanonJobOut(BaseModel):
    id: int
    reference_id: int
    status: str
    model: Optional[str] = None
    chunk_total: int
    chunk_done: int
    failed_chunks: int
    entity_count: int
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True, protected_namespaces=())
