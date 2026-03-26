"""扩写模块模型测试"""
import pytest
from app.models.expansion_project import ExpansionProject
from app.models.expansion_segment import ExpansionSegment


class TestExpansionProjectModel:
    """ExpansionProject 模型字段测试"""

    def test_tablename(self):
        assert ExpansionProject.__tablename__ == "expansion_projects"

    def test_required_fields(self):
        """验证必须字段存在"""
        columns = {c.name for c in ExpansionProject.__table__.columns}
        required = {"id", "user_id", "title", "source_type", "original_text",
                     "word_count", "expansion_level", "status", "execution_mode",
                     "version", "created_at"}
        assert required.issubset(columns)

    def test_optional_fields(self):
        """验证可选字段存在"""
        columns = {c.name for c in ExpansionProject.__table__.columns}
        optional = {"summary", "style_profile", "target_word_count",
                     "style_instructions", "ai_config", "metadata", "source_ref"}
        assert optional.issubset(columns)

    def test_status_default(self):
        col = ExpansionProject.__table__.columns["status"]
        assert col.default.arg == "created"

    def test_version_default(self):
        col = ExpansionProject.__table__.columns["version"]
        assert col.default.arg == 1

    def test_execution_mode_default(self):
        col = ExpansionProject.__table__.columns["execution_mode"]
        assert col.default.arg == "auto"


class TestExpansionSegmentModel:
    """ExpansionSegment 模型字段测试"""

    def test_tablename(self):
        assert ExpansionSegment.__tablename__ == "expansion_segments"

    def test_required_fields(self):
        columns = {c.name for c in ExpansionSegment.__table__.columns}
        required = {"id", "project_id", "sort_order", "original_content",
                     "status", "original_word_count", "created_at"}
        assert required.issubset(columns)

    def test_optional_fields(self):
        columns = {c.name for c in ExpansionSegment.__table__.columns}
        optional = {"title", "expanded_content", "expansion_level",
                     "custom_instructions", "error_message", "expanded_word_count"}
        assert optional.issubset(columns)

    def test_status_default(self):
        col = ExpansionSegment.__table__.columns["status"]
        assert col.default.arg == "pending"

    def test_foreign_key(self):
        col = ExpansionSegment.__table__.columns["project_id"]
        fks = [fk.target_fullname for fk in col.foreign_keys]
        assert "expansion_projects.id" in fks