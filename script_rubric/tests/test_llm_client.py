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
