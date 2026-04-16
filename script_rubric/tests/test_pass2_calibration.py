from __future__ import annotations

from script_rubric.models import ScriptArchive, DimensionAnalysis
from script_rubric.config import DIMENSION_KEYS


def _make_archive(
    title: str,
    status: str,
    mean_score: float,
    genre: str = "都市言情",
    dim_score: int = 7,
) -> ScriptArchive:
    dims = {
        key: DimensionAnalysis(score=dim_score, verdict="mixed")
        for key in DIMENSION_KEYS
    }
    return ScriptArchive(
        title=title,
        status=status,
        genre=genre,
        mean_score=mean_score,
        score_range=(int(mean_score) - 2, int(mean_score) + 2),
        dimensions=dims,
        consensus_points=[f"{title} 共识1", f"{title} 共识2", f"{title} 共识3"],
        red_flags=[f"{title} 红旗A"],
        green_flags=[f"{title} 绿旗A"],
    )


def _sample_archives() -> list[ScriptArchive]:
    return [
        _make_archive("S1", "签", 79.0),
        _make_archive("S2", "签", 78.0),
        _make_archive("S3", "签", 77.0),
        _make_archive("R1", "改", 78.0),
        _make_archive("R2", "改", 75.0),
        _make_archive("R3", "改", 80.0),
        _make_archive("J1", "拒", 70.0),
        _make_archive("J2", "拒", 73.0),
        _make_archive("J3", "拒", 76.0),
    ]


class TestCalibrationStats:
    def test_section_has_all_statuses(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "签" in text
        assert "改" in text
        assert "拒" in text

    def test_section_has_correct_status_means(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        # 签: (79+78+77)/3 = 78.0; 改: (78+75+80)/3 = 77.7; 拒: (70+73+76)/3 = 73.0
        assert "78.0" in text
        assert "77.7" in text
        assert "73.0" in text

    def test_section_has_advisory_thresholds(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        # midpoints (banker's rounding): (78.0+77.7)/2 -> 77.8; (77.7+73.0)/2 -> 75.3
        assert "77.8" in text
        assert "75.3" in text
        assert "参考" in text or "刻度仅为参考" in text

    def test_section_has_overlap_warning(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "重叠" in text
        assert "质性" in text
