"""
文件解析服务
支持 txt、markdown、docx 格式的文件解析
"""
import re
from dataclasses import dataclass, field
from typing import List
from io import BytesIO


@dataclass
class ParseResult:
    """解析结果"""
    text: str
    word_count: int
    detected_structure: List[str] = field(default_factory=list)


class FileParser:
    """文件解析器"""

    MAX_CHARS = 30000

    @staticmethod
    def _decode(content: bytes) -> str:
        """尝试多种编码解码内容"""
        encodings = ["utf-8", "gbk", "gb2312", "gb18030"]

        for encoding in encodings:
            try:
                return content.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue

        raise ValueError("无法识别文件编码，请确保文件为 UTF-8、GBK、GB2312 或 GB18030 编码")

    @staticmethod
    def _count_words(text: str) -> int:
        """统计字数（中文字符 + 英文单词）"""
        # 统计中文字符
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))

        # 统计英文单词
        english_words = len(re.findall(r'[a-zA-Z]+', text))

        return chinese_chars + english_words

    @staticmethod
    def _validate_content(text: str) -> None:
        """验证内容有效性"""
        if not text or not text.strip():
            raise ValueError("空文件，无法解析")

        if len(text) > FileParser.MAX_CHARS:
            raise ValueError(f"文件内容超过 {FileParser.MAX_CHARS} 字符限制，当前 {len(text)} 字符")

    @staticmethod
    def parse_txt(content: bytes) -> ParseResult:
        """解析纯文本文件"""
        text = FileParser._decode(content)
        FileParser._validate_content(text)

        word_count = FileParser._count_words(text)

        return ParseResult(
            text=text,
            word_count=word_count,
            detected_structure=[]
        )

    @staticmethod
    def parse_markdown(content: bytes) -> ParseResult:
        """解析 Markdown 文件"""
        text = FileParser._decode(content)
        FileParser._validate_content(text)

        # 提取标题作为结构
        structure = []
        lines = text.split('\n')
        for line in lines:
            # 匹配 # 标题 格式
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                level = len(match.group(1))
                title = match.group(2).strip()
                structure.append(f"H{level}: {title}")

        # 移除 Markdown 格式标记，保留纯文本
        # 移除标题标记
        clean_text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # 移除粗体/斜体标记
        clean_text = re.sub(r'\*\*?([^\*]+)\*\*?', r'\1', clean_text)
        clean_text = re.sub(r'__?([^_]+)__?', r'\1', clean_text)
        # 移除链接，保留文本
        clean_text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean_text)
        # 移除代码块标记
        clean_text = re.sub(r'```[\s\S]*?```', '', clean_text)
        clean_text = re.sub(r'`([^`]+)`', r'\1', clean_text)
        # 移除列表标记
        clean_text = re.sub(r'^\s*[-*+]\s+', '', clean_text, flags=re.MULTILINE)
        clean_text = re.sub(r'^\s*\d+\.\s+', '', clean_text, flags=re.MULTILINE)

        word_count = FileParser._count_words(clean_text)

        return ParseResult(
            text=clean_text.strip(),
            word_count=word_count,
            detected_structure=structure
        )

    @staticmethod
    def parse_docx(content: bytes) -> ParseResult:
        """解析 Word 文档"""
        try:
            from docx import Document
        except ImportError:
            raise ImportError("需要安装 python-docx 库: pip install python-docx")

        # 从字节流创建文档
        doc = Document(BytesIO(content))

        # 提取所有段落文本
        paragraphs = []
        structure = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)

                # 检测标题样式
                if para.style and para.style.name:
                    style_name = para.style.name.lower()
                    if 'heading' in style_name or 'title' in style_name:
                        # 提取标题级别
                        level_match = re.search(r'heading\s*(\d)', style_name)
                        if level_match:
                            level = level_match.group(1)
                            structure.append(f"H{level}: {text}")
                        elif 'title' in style_name:
                            structure.append(f"H1: {text}")

        full_text = '\n'.join(paragraphs)
        FileParser._validate_content(full_text)

        word_count = FileParser._count_words(full_text)

        return ParseResult(
            text=full_text,
            word_count=word_count,
            detected_structure=structure
        )