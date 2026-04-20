from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, computed_field


class Review(BaseModel):
    reviewer: str
    score: int | None = None
    comment: str | None = None


class ScriptRecord(BaseModel):
    title: str
    source_type: str
    genre: str
    submitter: str
    status: str
    status_source: str = "confirmed"  # "confirmed" | "score_inferred"
    reviews: list[Review] = []
    text_content: str | None = None
    text_file: str | None = None

    @computed_field
    @property
    def mean_score(self) -> float | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if not scores:
            return None
        return round(sum(scores) / len(scores), 1)

    @computed_field
    @property
    def score_range(self) -> tuple[int, int] | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if not scores:
            return None
        return (min(scores), max(scores))

    @computed_field
    @property
    def score_std(self) -> float | None:
        scores = [r.score for r in self.reviews if r.score is not None]
        if len(scores) < 2:
            return None
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / (len(scores) - 1)
        return round(variance ** 0.5, 1)


class DimensionAnalysis(BaseModel):
    score: int
    verdict: Literal["positive", "mixed", "negative"]
    evidence_from_reviews: list[str] = []
    evidence_from_text: list[str] = []
    extracted_rule: str = ""


class ScriptArchive(BaseModel):
    title: str
    status: str
    genre: str
    mean_score: float
    score_range: tuple[int, int]
    dimensions: dict[str, DimensionAnalysis]
    type_specific_notes: str = ""
    consensus_points: list[str] = []
    disagreement_points: list[str] = []
    red_flags: list[str] = []
    green_flags: list[str] = []


class PredictResult(BaseModel):
    title: str
    predicted_score: int
    predicted_status: str
    dimension_scores: dict[str, int] = {}
    comments: list[str] = []
    red_flags_hit: list[str] = []
    green_flags_hit: list[str] = []


class BacktestMetrics(BaseModel):
    status_accuracy: float
    range_accuracy: float
    mae: float
    critical_miss_rate: float
    total: int
    details: list[dict] = []
