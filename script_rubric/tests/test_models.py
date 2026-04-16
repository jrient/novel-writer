from script_rubric.models import Review, ScriptRecord, DimensionAnalysis, ScriptArchive


class TestScriptRecord:
    def test_mean_score(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=80),
                Review(reviewer="R2", score=70),
                Review(reviewer="R3", score=90),
            ],
        )
        assert record.mean_score == 80.0

    def test_mean_score_with_none(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=80),
                Review(reviewer="R2", score=None, comment="好看"),
            ],
        )
        assert record.mean_score == 80.0

    def test_mean_score_empty(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签", reviews=[],
        )
        assert record.mean_score is None

    def test_score_range(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=65),
                Review(reviewer="R2", score=80),
                Review(reviewer="R3", score=100),
            ],
        )
        assert record.score_range == (65, 100)

    def test_score_std(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[
                Review(reviewer="R1", score=70),
                Review(reviewer="R2", score=80),
            ],
        )
        assert record.score_std is not None
        assert abs(record.score_std - 7.1) < 0.1

    def test_score_std_single_review(self):
        record = ScriptRecord(
            title="test", source_type="原创", genre="男频",
            submitter="A", status="签",
            reviews=[Review(reviewer="R1", score=80)],
        )
        assert record.score_std is None


class TestScriptArchive:
    def test_create_archive(self):
        archive = ScriptArchive(
            title="test", status="签", genre="男频",
            mean_score=80.0, score_range=(75, 85),
            dimensions={
                "premise_innovation": DimensionAnalysis(
                    score=8, verdict="positive",
                    evidence_from_reviews=["设定新颖"],
                    extracted_rule="多元素交叉设定有优势",
                ),
            },
        )
        assert archive.dimensions["premise_innovation"].score == 8
