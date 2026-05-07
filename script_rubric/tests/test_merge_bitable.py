"""merge_bitable_tables 单测。"""

from script_rubric.feishu.feishu_common import merge_bitable_tables, _extract_record_title


def _rec(title=None, fields=None):
    """快速构建模拟记录。"""
    if fields is None:
        fields = {}
    if title:
        fields["书名"] = title
    return {"record_id": f"r_{title or 'empty'}", "fields": fields}


def _table(name, records):
    return {
        "table_id": f"tid_{name}",
        "table_name": name,
        "fields": [{"field_name": "书名"}],
        "records": records,
    }


class TestExtractRecordTitle:
    def test_with_title(self):
        rec = _rec("测试剧本")
        assert _extract_record_title(rec) == "测试剧本"

    def test_with_text_field(self):
        rec = {"fields": {"文本": "AI仿真人剧本"}}
        assert _extract_record_title(rec) == "AI仿真人剧本"

    def test_empty_fields(self):
        rec = _rec()
        assert _extract_record_title(rec) is None

    def test_whitespace_only(self):
        rec = {"fields": {"书名": "   "}}
        assert _extract_record_title(rec) is None


class TestMergeBitableTables:
    def test_self_merge_no_duplicates(self):
        """相同数据自合并：无追加，总数不变。"""
        records = [_rec("A"), _rec("B")]
        tables = [_table("冲量", records)]

        merged, stats = merge_bitable_tables(tables, tables)

        assert stats["appended"] == 0
        assert sum(len(t["records"]) for t in merged) == 2

    def test_new_record_appended(self):
        """新数据中有旧数据没有的标题，应追加。"""
        old = [_table("冲量", [_rec("旧剧本")])]
        new = [_table("冲量", [_rec("旧剧本"), _rec("新剧本")])]

        merged, stats = merge_bitable_tables(old, new)

        assert stats["appended"] == 1
        assert stats["updated"] == 1
        assert sum(len(t["records"]) for t in merged) == 2

    def test_old_record_retained(self):
        """旧数据中有新数据没有的标题，应保留。"""
        old = [_table("冲量", [_rec("旧剧本"), _rec("保留剧本")])]
        new = [_table("冲量", [_rec("旧剧本")])]

        merged, stats = merge_bitable_tables(old, new)

        assert stats["retained"] == 1
        assert stats["updated"] == 1
        assert sum(len(t["records"]) for t in merged) == 2

    def test_updated_record_uses_new_data(self):
        """匹配到的标题应使用新数据。"""
        old = [_table("冲量", [_rec("剧本", {"书名": "剧本", "字段": "旧值"})])]
        new = [_table("冲量", [_rec("剧本", {"书名": "剧本", "字段": "新值"})])]

        merged, stats = merge_bitable_tables(old, new)

        assert stats["updated"] == 1
        rec = merged[0]["records"][0]
        assert rec["fields"]["字段"] == "新值"

    def test_multi_table_merge(self):
        """多表合并时 retained 应跨表累加。"""
        old = [
            _table("冲量", [_rec("A")]),
            _table("精品", [_rec("B"), _rec("C")]),
        ]
        new = [
            _table("冲量", [_rec("A")]),
            _table("精品", [_rec("B")]),
        ]

        merged, stats = merge_bitable_tables(old, new)

        assert stats["retained"] == 1  # 精品表中 C 被保留
        assert stats["updated"] == 2
        assert sum(len(t["records"]) for t in merged) == 3

    def test_new_table_added(self):
        """新数据源中有旧数据源没有的表。"""
        old = [_table("冲量", [_rec("A")])]
        new = [
            _table("冲量", [_rec("A")]),
            _table("精品", [_rec("B")]),
        ]

        merged, stats = merge_bitable_tables(old, new)

        assert len(merged) == 2
        assert stats["appended"] == 1

    def test_old_table_retained(self):
        """旧数据源中有但新数据源没有的表。"""
        old = [
            _table("冲量", [_rec("A")]),
            _table("精品", [_rec("B")]),
        ]
        new = [_table("冲量", [_rec("A")])]

        merged, stats = merge_bitable_tables(old, new)

        assert len(merged) == 2
        assert stats["retained"] == 1
        titles = {_extract_record_title(r) for t in merged for r in t["records"]}
        assert "B" in titles
