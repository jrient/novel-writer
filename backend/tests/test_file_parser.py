"""文件解析器测试"""
import pytest
from app.services.file_parser import FileParser, ParseResult


class TestFileParser:
    def test_parse_txt_utf8(self):
        content = "这是一段测试文本。包含中文内容。".encode("utf-8")
        result = FileParser.parse_txt(content)
        assert isinstance(result, ParseResult)
        assert "测试文本" in result.text
        assert result.word_count > 0

    def test_parse_txt_gbk(self):
        content = "这是GBK编码的文本。".encode("gbk")
        result = FileParser.parse_txt(content)
        assert "GBK编码" in result.text

    def test_parse_markdown(self):
        content = "# 标题\n\n这是正文内容。\n\n## 子标题\n\n更多内容。".encode("utf-8")
        result = FileParser.parse_markdown(content)
        assert "标题" in result.text
        assert "正文内容" in result.text
        assert len(result.detected_structure) > 0

    def test_parse_empty_raises(self):
        with pytest.raises(ValueError, match="空文件"):
            FileParser.parse_txt(b"")

    def test_parse_too_long_raises(self):
        content = ("字" * 30001).encode("utf-8")
        with pytest.raises(ValueError, match="30000"):
            FileParser.parse_txt(content)

    def test_word_count_chinese(self):
        content = "这是十个中文字符的文本".encode("utf-8")
        result = FileParser.parse_txt(content)
        # "这是十个中文字符的文本" has 11 Chinese characters
        assert result.word_count == 11

    def test_detect_encoding_fallback(self):
        """无法解码的内容应抛出错误"""
        invalid_bytes = bytes(range(128, 256))
        with pytest.raises(ValueError, match="编码"):
            FileParser.parse_txt(invalid_bytes)