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


class TestAnchorSelection:
    def test_anchor_per_status_present(self):
        from script_rubric.pipeline.pass2_synthesize import _build_calibration_section

        text = _build_calibration_section(_sample_archives())
        assert "锚点" in text
        # 签 mean=78.0 -> S2 (78.0); 改 mean=77.7 -> R1 (78.0, |.3| smallest);
        # 拒 mean=73.0 -> J2 (73.0)
        assert "S2" in text
        assert "R1" in text
        assert "J2" in text

    def test_anchor_closest_to_mean_wins(self):
        from script_rubric.pipeline.pass2_synthesize import _select_anchor

        archives = [
            _make_archive("A", "改", 70.0),
            _make_archive("B", "改", 78.0),
            _make_archive("C", "改", 79.0),
        ]
        # mean = 75.67, closest = B (|78-75.67| = 2.33 < |79-75.67| = 3.33 < |70-75.67| = 5.67)
        anchor = _select_anchor(archives, target_mean=75.67)
        assert anchor.title == "B"

    def test_anchor_tiebreak_by_title(self):
        from script_rubric.pipeline.pass2_synthesize import _select_anchor

        archives = [
            _make_archive("Z", "改", 76.0),
            _make_archive("A", "改", 76.0),
        ]
        # both equidistant from 76 -> A wins by title sort
        anchor = _select_anchor(archives, target_mean=76.0)
        assert anchor.title == "A"


class TestHandbookIntegration:
    def test_calibration_appears_as_part_four(self, tmp_path, monkeypatch):
        import script_rubric.pipeline.pass2_synthesize as p2

        monkeypatch.setattr(p2, "HANDBOOK_DIR", tmp_path)

        async def fake_universal(archives, confirmed_titles=None):
            return "通用规律占位"

        async def fake_overlay(archives, genre):
            return f"{genre} 占位"

        async def fake_redflags(rejected, borderline):
            return "地雷占位"

        monkeypatch.setattr(p2, "synthesize_universal", fake_universal)
        monkeypatch.setattr(p2, "synthesize_overlay", fake_overlay)
        monkeypatch.setattr(p2, "synthesize_redflags", fake_redflags)

        import asyncio
        handbook, _ = asyncio.run(p2.synthesize_all(_sample_archives(), version=99))

        assert "## 第四部分：评分校准刻度" in handbook
        # Part 4 must come before appendix
        assert handbook.index("## 第四部分：评分校准刻度") < handbook.index("## 附录")
        # Calibration content must be present
        assert "状态-分数分布表" in handbook
        assert "锚点" in handbook


class TestCmdPass2Filter:
    def test_pass2_filters_to_training_set(self, monkeypatch):
        import script_rubric.pipeline.run as run

        from script_rubric.models import ScriptRecord, Review
        records = [
            ScriptRecord(
                title=f"T{i}", source_type="x", genre="y",
                submitter="z", status="改",
                reviews=[Review(reviewer="a", score=75)],
            )
            for i in range(5)
        ]

        archives = [_make_archive(f"T{i}", "改", 75.0) for i in range(5)]

        captured = {}

        async def fake_synth(passed_archives, version, confirmed_titles=None):
            captured["titles"] = [a.title for a in passed_archives]
            return "handbook", {}

        monkeypatch.setattr(run, "parse_xlsx", lambda *a, **kw: records)
        monkeypatch.setattr(run, "match_texts", lambda *a, **kw: None)
        monkeypatch.setattr(run, "load_all_archives", lambda: archives)
        monkeypatch.setattr(run, "synthesize_all", fake_synth)

        import asyncio
        from argparse import Namespace
        asyncio.run(run.cmd_pass2_only(Namespace(version=4)))

        # split_holdout(seed=42, ratio=0.2) on 5 改-records: n_test = max(1, round(1.0)) = 1
        assert len(captured["titles"]) == 4
        assert len(set(captured["titles"])) == 4
