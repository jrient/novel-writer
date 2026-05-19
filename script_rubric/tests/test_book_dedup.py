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


import json
from pathlib import Path

import pytest

from script_rubric.feishu.record_store import rebuild_index, save_record, save_table_meta


@pytest.fixture
def temp_records_root(tmp_path, monkeypatch):
    """临时 RECORDS_ROOT，避免污染真实数据。"""
    fake_root = tmp_path / "bitable_records"
    fake_root.mkdir()
    monkeypatch.setattr("script_rubric.feishu.record_store.RECORDS_ROOT", fake_root)
    return fake_root


def _write_record(root, table_id, table_name, record_id, title, synced_at, app_token="app_x"):
    """直接落盘一条 per-record 文件，绕过 sync 流程。"""
    tdir = root / table_id
    tdir.mkdir(exist_ok=True)
    meta = tdir / "_meta.json"
    if not meta.exists():
        meta.write_text(json.dumps({
            "table_id": table_id,
            "table_name": table_name,
            "fields": [{"field_name": "书名"}],
            "_updated_at": synced_at,
            "_source_app_token": app_token,
        }, ensure_ascii=False), encoding="utf-8")
    rec_path = tdir / f"{record_id}.json"
    rec_path.write_text(json.dumps({
        "record_id": record_id,
        "fields": {"书名": title},
        "_record_id": record_id,
        "_synced_at": synced_at,
        "_source_app_token": app_token,
    }, ensure_ascii=False), encoding="utf-8")


class TestRebuildIndexDedup:
    def test_dedup_keeps_latest_across_table_ids(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_old", "精品", "r1", "某书", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_new", "精品", "r2", "某书", "2026-05-18T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        precision_tables = [t for t in index["tables"] if t["table_name"] == "精品"]
        assert len(precision_tables) == 1
        records = precision_tables[0]["records"]
        assert len(records) == 1
        assert records[0]["fields"]["书名"] == "某书"
        assert records[0]["record_id"] == "r2"

    def test_dedup_stats_emitted(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "A", "2026-05-18T10:00:00")
        _write_record(temp_records_root, "tid_c", "精品", "r3", "B", "2026-05-18T10:00:00")
        tdir = temp_records_root / "tid_a"
        (tdir / "r_empty.json").write_text(json.dumps({
            "record_id": "r_empty", "fields": {},
            "_record_id": "r_empty", "_synced_at": "2026-05-01T10:00:00",
        }, ensure_ascii=False), encoding="utf-8")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        stats = index["_dedup_stats"]
        assert stats["unique_books"] == 2
        assert stats["dropped_duplicates"] == 1
        assert stats["skipped_no_title"] == 1
        assert stats["total_files"] == 4

        dropped = index["_dedup_dropped"]
        assert len(dropped) == 1
        assert dropped[0]["title"] == "A"

    def test_cross_table_winner_in_its_table_only(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_chong", "冲量", "r1", "某书", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_jing", "精品", "r2", "某书", "2026-05-18T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        chong = [t for t in index["tables"] if t["table_name"] == "冲量"][0]
        jing = [t for t in index["tables"] if t["table_name"] == "精品"][0]
        assert len(chong["records"]) == 0
        assert len(jing["records"]) == 1
        assert jing["records"][0]["record_id"] == "r2"

    def test_rebuild_idempotent_ignoring_timestamp(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-18T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "A", "2026-05-01T10:00:00")

        out1 = tmp_path / "out1.json"
        out2 = tmp_path / "out2.json"
        idx1 = rebuild_index(out1, latest_app_token="app_x")
        idx2 = rebuild_index(out2, latest_app_token="app_x")

        for d in (idx1, idx2):
            d.pop("synced_at")
        assert idx1 == idx2

    def test_same_table_name_multiple_dirs_merged(self, temp_records_root, tmp_path):
        _write_record(temp_records_root, "tid_a", "精品", "r1", "A", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_b", "精品", "r2", "B", "2026-05-01T10:00:00")
        _write_record(temp_records_root, "tid_c", "精品", "r3", "C", "2026-05-01T10:00:00")

        out = tmp_path / "out.json"
        index = rebuild_index(out, latest_app_token="app_x")

        jing_tables = [t for t in index["tables"] if t["table_name"] == "精品"]
        assert len(jing_tables) == 1
        titles = sorted(r["fields"]["书名"] for r in jing_tables[0]["records"])
        assert titles == ["A", "B", "C"]
