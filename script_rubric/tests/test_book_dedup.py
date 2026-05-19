"""书级去重逻辑单测。"""

from script_rubric.feishu.book_dedup import (
    normalize_title,
    select_winner,
    dedup_by_book,
)


class TestNormalizeTitle:
    def test_strip_whitespace(self):
        assert normalize_title("  某书  ") == "某书"

    def test_strip_book_brackets(self):
        assert normalize_title("《某书》") == "某书"

    def test_strip_brackets_and_whitespace(self):
        assert normalize_title("  《某书》 ") == "某书"

    def test_empty_returns_empty(self):
        assert normalize_title("") == ""

    def test_none_returns_empty(self):
        assert normalize_title(None) == ""

    def test_inner_whitespace_kept(self):
        assert normalize_title("某 书") == "某 书"


class TestSelectWinner:
    def _rec(self, record_id, synced_at, title="某书"):
        return {
            "fields": {"书名": title},
            "_record_id": record_id,
            "_synced_at": synced_at,
            "_source_table_id": "tid_x",
        }

    def test_latest_synced_at_wins(self):
        a = self._rec("r1", "2026-05-01T10:00:00")
        b = self._rec("r2", "2026-05-18T10:00:00")
        c = self._rec("r3", "2026-05-07T10:00:00")
        winner, dropped = select_winner([a, b, c])
        assert winner is b
        assert set(d["_record_id"] for d in dropped) == {"r1", "r3"}

    def test_tiebreak_by_record_id_dictionary_order(self):
        same_time = "2026-05-18T10:00:00"
        a = self._rec("r_aaa", same_time)
        b = self._rec("r_zzz", same_time)
        winner, _ = select_winner([a, b])
        assert winner is b

    def test_missing_synced_at_loses_to_anything(self):
        old = self._rec("r1", "")
        old.pop("_synced_at")
        new = self._rec("r2", "2020-01-01T00:00:00")
        winner, _ = select_winner([old, new])
        assert winner is new

    def test_single_record_is_winner(self):
        rec = self._rec("r1", "2026-05-18T10:00:00")
        winner, dropped = select_winner([rec])
        assert winner is rec
        assert dropped == []


class TestDedupByBook:
    def _rec(self, record_id, synced_at, title, table_id="tid_x", app_token="app_x"):
        return {
            "fields": {"书名": title},
            "_record_id": record_id,
            "_synced_at": synced_at,
            "_source_app_token": app_token,
        }, table_id

    def test_no_duplicates_no_op(self):
        a, _ = self._rec("r1", "2026-05-01T10:00:00", "A")
        b, _ = self._rec("r2", "2026-05-01T10:00:00", "B")
        winners, dropped, skipped = dedup_by_book([(a, "tid_a"), (b, "tid_b")])
        assert len(winners) == 2
        assert dropped == []
        assert skipped == 0

    def test_dup_titles_keep_latest(self):
        old, _ = self._rec("r1", "2026-05-01T10:00:00", "某书")
        new, _ = self._rec("r2", "2026-05-18T10:00:00", "某书")
        winners, dropped, skipped = dedup_by_book([(old, "tid_old"), (new, "tid_new")])
        assert len(winners) == 1
        assert winners[0][0]["_record_id"] == "r2"
        assert len(dropped) == 1
        assert dropped[0]["title"] == "某书"
        assert dropped[0]["kept_from"] == "tid_new/r2"
        assert dropped[0]["dropped_from"] == "tid_old/r1"

    def test_normalized_title_groups_variants(self):
        a, _ = self._rec("r1", "2026-05-01T10:00:00", "《某书》")
        b, _ = self._rec("r2", "2026-05-18T10:00:00", "某书 ")
        winners, dropped, skipped = dedup_by_book([(a, "tid_a"), (b, "tid_b")])
        assert len(winners) == 1
        assert winners[0][0]["_record_id"] == "r2"

    def test_no_title_records_skipped(self):
        good, _ = self._rec("r1", "2026-05-01T10:00:00", "A")
        bad = {"_record_id": "r2", "_synced_at": "2026-05-01T10:00:00", "fields": {}}
        winners, dropped, skipped = dedup_by_book([(good, "tid_a"), (bad, "tid_b")])
        assert len(winners) == 1
        assert skipped == 1
        assert dropped == []
