"""改编模块 Pydantic 出入参 schema。"""
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field

EntityType = Literal["person", "place", "prop", "era_term", "other"]


class AdaptationProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    raw_text: Optional[str] = None
    intent: Optional[str] = None
    intensity: int = Field(default=2, ge=1, le=3)
    era_target: Optional[str] = None


class AdaptationProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    intent: Optional[str] = None
    intensity: Optional[int] = Field(default=None, ge=1, le=3)
    era_target: Optional[str] = None


class MappingEntryIn(BaseModel):
    entity_type: EntityType
    original_text: str = Field(min_length=1, max_length=200)
    replacement_text: Optional[str] = Field(default=None, max_length=200)
    locked: bool = False
    notes: Optional[str] = None
    order_index: int = 0


class MappingEntryOut(MappingEntryIn):
    id: int


class MappingsBulkPut(BaseModel):
    entries: List[MappingEntryIn]


class SceneBoundary(BaseModel):
    index: int
    start: int
    end: int
    title: str


class AdaptationProjectOut(BaseModel):
    id: int
    title: str
    source_filename: Optional[str]
    intent: Optional[str]
    intensity: int
    era_target: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    word_count: int
    scene_boundaries: List[SceneBoundary] = []
    versions: List["AdaptationVersionOut"] = []
    mappings: List[MappingEntryOut] = []

    model_config = {"from_attributes": True}


class AdaptationVersionOut(BaseModel):
    id: int
    version_no: int
    triggered_by: str
    status: str
    stats: Optional[dict]
    error: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SceneResultOut(BaseModel):
    id: int
    scene_index: int
    scene_title: Optional[str]
    status: str
    error: Optional[str]
    token_used: Optional[int]
    line_count_delta_pct: Optional[float]
    original_scene_text: str
    rewritten_scene_text: Optional[str]
    manual_edits: Optional[list] = []
    updated_at: datetime

    model_config = {"from_attributes": True}


class VersionDetailOut(AdaptationVersionOut):
    scene_results: List[SceneResultOut] = []


class RunCreate(BaseModel):
    extra_prompt: Optional[str] = None


class SceneRerunRequest(BaseModel):
    extra_prompt: Optional[str] = None


class SceneManualPatch(BaseModel):
    rewritten_scene_text: str = Field(min_length=0)


class MappingSuggestRequest(BaseModel):
    only_empty: bool = True
