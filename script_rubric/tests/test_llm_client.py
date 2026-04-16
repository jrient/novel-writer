from script_rubric.pipeline.llm_client import extract_json


class TestExtractJson:
    def test_plain_json(self):
        text = '{"a": 1, "b": "hello"}'
        assert extract_json(text) == {"a": 1, "b": "hello"}

    def test_fenced_json(self):
        text = '```json\n{"a": 1}\n```'
        assert extract_json(text) == {"a": 1}

    def test_fenced_no_lang(self):
        text = '```\n{"a": 1}\n```'
        assert extract_json(text) == {"a": 1}

    def test_with_surrounding_text(self):
        text = 'Here is the result:\n```json\n{"x": 42}\n```\nDone.'
        assert extract_json(text) == {"x": 42}

    def test_nested(self):
        text = '```json\n{"dims": {"a": {"score": 8}}}\n```'
        result = extract_json(text)
        assert result["dims"]["a"]["score"] == 8

    def test_unfenced_with_prose(self):
        text = '好的，下面是分析结果：\n{"a": 1, "b": [2, 3]}\n以上。'
        assert extract_json(text) == {"a": 1, "b": [2, 3]}

    def test_fenced_with_trailing_prose(self):
        text = '```json\n{"a": 1}\n```\n\n附注：以上是结果。'
        assert extract_json(text) == {"a": 1}

    def test_repair_missing_comma(self):
        text = '{"a": 1 "b": 2}'
        result = extract_json(text)
        assert result == {"a": 1, "b": 2}
