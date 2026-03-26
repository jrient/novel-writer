"""扩写模块 Schema 测试"""
import pytest
from pydantic import ValidationError
from app.schemas.expansion import (
    ExpansionProjectCreate, ExpansionProjectUpdate, ExpansionProjectResponse,
    ExpansionSegmentResponse, ExpansionSegmentUpdate,
    SegmentSplitRequest, SegmentMergeRequest,
    ImportFromNovelRequest, ImportFromDramaRequest,
    ConvertRequest, StyleProfile,
    VALID_EXPANSION_LEVELS, VALID_SOURCE_TYPES, VALID_EXECUTION_MODES,
)


class TestExpansionProjectCreate:
    def test_valid_manual(self):
        data = ExpansionProjectCreate(
            title="测试扩写", source_type="manual",
            original_text="这是原文内容。" * 100,
        )
        assert data.title == "测试扩写"
        assert data.source_type == "manual"

    def test_title_required(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(source_type="manual", original_text="abc")

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="invalid", original_text="abc"
            )

    def test_invalid_expansion_level(self):
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="manual",
                original_text="abc", expansion_level="extreme"
            )

    def test_word_count_limit(self):
        """超过 30000 字应该被拒绝"""
        long_text = "字" * 30001
        with pytest.raises(ValidationError):
            ExpansionProjectCreate(
                title="test", source_type="manual", original_text=long_text
            )


class TestExpansionProjectUpdate:
    def test_partial_update(self):
        data = ExpansionProjectUpdate(expansion_level="deep")
        assert data.expansion_level == "deep"
        assert data.title is None

    def test_invalid_level(self):
        with pytest.raises(ValidationError):
            ExpansionProjectUpdate(expansion_level="invalid")


class TestSegmentRequests:
    def test_split_request(self):
        data = SegmentSplitRequest(segment_id=1, split_position=500)
        assert data.split_position == 500

    def test_split_negative_position(self):
        with pytest.raises(ValidationError):
            SegmentSplitRequest(segment_id=1, split_position=-1)

    def test_merge_request(self):
        data = SegmentMergeRequest(segment_ids=[1, 2])
        assert len(data.segment_ids) == 2

    def test_merge_single_segment(self):
        with pytest.raises(ValidationError):
            SegmentMergeRequest(segment_ids=[1])


class TestConvertRequest:
    def test_valid_target(self):
        data = ConvertRequest(target="novel")
        assert data.target == "novel"

    def test_invalid_target(self):
        with pytest.raises(ValidationError):
            ConvertRequest(target="other")


class TestStyleProfile:
    def test_valid_profile(self):
        profile = StyleProfile(
            narrative_pov="第三人称",
            tone="轻松",
            sentence_style="短句为主",
            vocabulary="口语化",
            rhythm="节奏快",
        )
        assert profile.narrative_pov == "第三人称"