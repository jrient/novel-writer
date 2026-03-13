"""
事件与剧情线 Pydantic 模式
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


# ============ Plotline ============

class PlotlineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#6B7B8D"
    sort_order: int = 0


class PlotlineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    color: Optional[str] = None
    sort_order: Optional[int] = None


class PlotlineResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    description: Optional[str] = None
    color: str
    sort_order: int
    created_at: datetime
    updated_at: Optional[datetime] = None


# ============ StoryEvent ============

class StoryEventCreate(BaseModel):
    title: str
    description: Optional[str] = None
    event_type: str = "plot_point"
    status: str = "planned"
    anchor_type: Optional[str] = None
    anchor_id: Optional[str] = None
    plotline_ids: List[int] = []
    timeline_order: int = 0
    time_label: Optional[str] = None
    character_ids: List[int] = []
    location_map_id: Optional[str] = None
    cause_event_ids: List[int] = []
    effect_event_ids: List[int] = []
    foreshadow_event_id: Optional[int] = None
    tags: List[str] = []
    importance: str = "major"
    sort_order: Optional[int] = None


class StoryEventUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    event_type: Optional[str] = None
    status: Optional[str] = None
    anchor_type: Optional[str] = None
    anchor_id: Optional[str] = None
    plotline_ids: Optional[List[int]] = None
    timeline_order: Optional[int] = None
    time_label: Optional[str] = None
    character_ids: Optional[List[int]] = None
    location_map_id: Optional[str] = None
    cause_event_ids: Optional[List[int]] = None
    effect_event_ids: Optional[List[int]] = None
    foreshadow_event_id: Optional[int] = None
    tags: Optional[List[str]] = None
    importance: Optional[str] = None
    sort_order: Optional[int] = None


class StoryEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    title: str
    description: Optional[str] = None
    event_type: str
    status: str
    anchor_type: Optional[str] = None
    anchor_id: Optional[str] = None
    plotline_ids: List[int] = []
    timeline_order: int
    time_label: Optional[str] = None
    character_ids: List[int] = []
    location_map_id: Optional[str] = None
    cause_event_ids: List[int] = []
    effect_event_ids: List[int] = []
    foreshadow_event_id: Optional[int] = None
    tags: List[str] = []
    importance: str
    sort_order: int
    created_at: datetime
    updated_at: Optional[datetime] = None
