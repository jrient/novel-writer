from script_rubric.pipeline.parse_xlsx import parse_xlsx, save_parsed, load_parsed
from script_rubric.config import XLSX_PATH


class TestParseXlsx:
    def test_parse_returns_list(self):
        records = parse_xlsx(XLSX_PATH)
        assert isinstance(records, list)
        assert len(records) > 0

    def test_valid_rows_only(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            assert r.status in ("签", "改", "拒"), f"Invalid status: {r.status}"
            scores = [rev.score for rev in r.reviews if rev.score is not None]
            assert len(scores) > 0, f"No scores for: {r.title}"

    def test_title_not_empty(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            assert r.title.strip(), "Empty title found"

    def test_reviews_have_reviewer_names(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            for rev in r.reviews:
                assert rev.reviewer, "Reviewer name is empty"

    def test_scores_in_range(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            for rev in r.reviews:
                if rev.score is not None:
                    assert 0 <= rev.score <= 100, f"Score out of range: {rev.score}"

    def test_genre_values(self):
        records = parse_xlsx(XLSX_PATH)
        valid_genres = {"男频", "女频", "萌宝", "世情"}
        for r in records:
            if r.genre:
                assert r.genre in valid_genres or r.genre == "", \
                    f"Unknown genre: {r.genre} for {r.title}"

    def test_computed_scores(self):
        records = parse_xlsx(XLSX_PATH)
        for r in records:
            if r.mean_score is not None:
                assert 0 <= r.mean_score <= 100

    def test_save_and_load_json(self, tmp_path):
        records = parse_xlsx(XLSX_PATH)
        out = tmp_path / "scripts.json"
        save_parsed(records, out)
        assert out.exists()
        loaded = load_parsed(out)
        assert len(loaded) == len(records)
        assert loaded[0].title == records[0].title
