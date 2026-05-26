from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class ProseProjectCreate(BaseModel):
    script_project_id: int
    premise: str = Field(min_length=1, max_length=500)
    title: Optional[str] = None
    genre: Optional[str] = None


class ProseSceneOut(BaseModel):
    id: int
    scene_index: int
    scene_title: str
    original_scene_text: str
    prose_text: Optional[str]
    status: str
    error: Optional[str]
    token_used: int

    model_config = ConfigDict(from_attributes=True)


class ProseProjectOut(BaseModel):
    id: int
    user_id: int
    title: str
    script_project_id: int
    script_project_title: Optional[str]
    premise: str
    genre: Optional[str]
    style_snapshot: Optional[str]
    status: str
    total_scenes: int
    done_scenes: int
    failed_scenes: int
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ProseProjectDetail(ProseProjectOut):
    scenes: list[ProseSceneOut] = Field(default_factory=list)
