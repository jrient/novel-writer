from script_rubric.models import ScriptRecord, Review, PredictResult
from script_rubric.pipeline.backtest import (
    split_holdout,
    evaluate_predictions,
)


class TestSplitHoldout:
    def test_split_ratio(self, sample_records):
        records = []
        for i in range(12):
            base = sample_records[i % len(sample_records)]
            records.append(base.model_copy(update={"title": f"Script_{i}"}))
        train, test = split_holdout(records, ratio=0.2, seed=42)
        assert len(test) >= 2
        assert len(train) + len(test) == len(records)

    def test_stratified_by_status(self):
        records = []
        for i in range(6):
            records.append(ScriptRecord(
                title=f"签_{i}", source_type="原创", genre="男频",
                submitter="A", status="签",
                reviews=[Review(reviewer="R", score=85)],
            ))
        for i in range(4):
            records.append(ScriptRecord(
                title=f"改_{i}", source_type="原创", genre="女频",
                submitter="A", status="改",
                reviews=[Review(reviewer="R", score=75)],
            ))
        for i in range(5):
            records.append(ScriptRecord(
                title=f"拒_{i}", source_type="原创", genre="男频",
                submitter="A", status="拒",
                reviews=[Review(reviewer="R", score=60)],
            ))
        train, test = split_holdout(records, ratio=0.2, seed=42)
        test_statuses = {r.status for r in test}
        assert len(test_statuses) >= 2

    def test_deterministic(self, sample_records):
        records = []
        for i in range(12):
            base = sample_records[i % len(sample_records)]
            records.append(base.model_copy(update={"title": f"Script_{i}"}))
        _, t1_test = split_holdout(records, ratio=0.2, seed=42)
        _, t2_test = split_holdout(records, ratio=0.2, seed=42)
        assert [r.title for r in t1_test] == [r.title for r in t2_test]


class TestEvaluatePredictions:
    def test_perfect_predictions(self):
        actuals = [
            ScriptRecord(
                title="A", source_type="原创", genre="男频",
                submitter="X", status="签",
                reviews=[Review(reviewer="R", score=80), Review(reviewer="R2", score=85)],
            ),
            ScriptRecord(
                title="B", source_type="原创", genre="女频",
                submitter="X", status="拒",
                reviews=[Review(reviewer="R", score=60), Review(reviewer="R2", score=65)],
            ),
        ]
        predictions = [
            PredictResult(title="A", predicted_score=82, predicted_status="签"),
            PredictResult(title="B", predicted_score=62, predicted_status="拒"),
        ]
        metrics = evaluate_predictions(predictions, actuals)
        assert metrics.status_accuracy == 1.0
        assert metrics.range_accuracy == 1.0
        assert metrics.critical_miss_rate == 0.0

    def test_critical_miss(self):
        actuals = [
            ScriptRecord(
                title="A", source_type="原创", genre="男频",
                submitter="X", status="签",
                reviews=[Review(reviewer="R", score=80)],
            ),
        ]
        predictions = [
            PredictResult(title="A", predicted_score=60, predicted_status="拒"),
        ]
        metrics = evaluate_predictions(predictions, actuals)
        assert metrics.critical_miss_rate == 1.0
