from script_rubric.models import ScriptRecord, Review
from script_rubric.pipeline.match_texts import match_texts, fuzzy_match_score


class TestFuzzyMatch:
    def test_exact_match(self):
        score = fuzzy_match_score("《八零福星俏娇妻》", "《八零福星俏娇妻》.txt")
        assert score > 0.8

    def test_partial_match(self):
        score = fuzzy_match_score(
            "改编AI真人剧《嫡女贵凰：重生毒妃狠绝色》（1）",
            "改编AI真人剧《嫡女贵凰：重生毒妃狠绝色》（1）.txt",
        )
        assert score > 0.8

    def test_no_match(self):
        score = fuzzy_match_score("完全不同的标题", "另一个文件.txt")
        assert score < 0.5


class TestMatchTexts:
    def test_match_with_real_data(self):
        from script_rubric.config import XLSX_PATH, DRAMA_DIR
        from script_rubric.pipeline.parse_xlsx import parse_xlsx

        records = parse_xlsx(XLSX_PATH)
        result = match_texts(records, DRAMA_DIR)

        matched = sum(1 for r in result.records if r.text_content is not None)
        assert matched > 0, "No texts matched"
        assert result.total == len(records)
        assert result.matched == matched

    def test_missing_dir(self, tmp_path):
        records = [
            ScriptRecord(
                title="test", source_type="原创", genre="男频",
                submitter="A", status="签",
                reviews=[Review(reviewer="R1", score=80)],
            ),
        ]
        fake = tmp_path / "does_not_exist"
        result = match_texts(records, fake)
        assert result.matched == 0

    def test_report_generated(self):
        from script_rubric.config import XLSX_PATH, DRAMA_DIR
        from script_rubric.pipeline.parse_xlsx import parse_xlsx

        records = parse_xlsx(XLSX_PATH)
        result = match_texts(records, DRAMA_DIR)
        report = result.to_report()
        assert "Total scripts" in report
        assert "Matched" in report
