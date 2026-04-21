"""
HandbookProvider — 加载并解析剧本评审手册（handbook_vN.md）
将 markdown 解析为结构化片段，按阶段/类型提供裁剪后的文本。
"""
import logging
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class HandbookProvider:
    """从 handbook 文件加载知识，提供按类型检索的片段"""

    def __init__(self, handbook_dir: Optional[str] = None):
        self.handbook_dir = Path(handbook_dir) if handbook_dir else (
            Path(__file__).parent.parent.parent.parent / "script_rubric" / "outputs" / "handbook"
        )
        self._version: str = "unknown"
        self._raw_text: str = ""
        self._universal_rules: str = ""
        self._genre_overlays: dict[str, str] = {}
        self._red_flags: str = ""
        self._question_slots: dict[str, list[dict]] = {}
        self.load()

    # ── Public ──

    @property
    def version(self) -> str:
        return self._version

    def is_loaded(self) -> bool:
        return bool(self._raw_text)

    def get_red_flags(self) -> str:
        """获取地雷清单（精简为条目列表），无数据返回空串"""
        return self._red_flags

    def get_universal_rules(self) -> str:
        """获取通用规律（7维度的可执行建议和量化锚点）"""
        return self._universal_rules

    def get_genre_overlay(self, genre: str) -> Optional[str]:
        """根据类型返回专项规律，无匹配返回 None"""
        if not genre:
            return None
        # 尝试多种匹配方式
        for key, text in self._genre_overlays.items():
            if key in genre or genre in key:
                return text
        # 模糊匹配：genre 包含关键字
        genre_lower = genre.lower()
        for kw in ["萌宝", "女频", "男频", "世情"]:
            if kw in genre_lower:
                for key, text in self._genre_overlays.items():
                    if kw in key:
                        return text
        return None

    def get_question_guidance(self, genre: str) -> str:
        """
        获取问答阶段的关键指导文本，用于注入 question prompt。
        包含通用规律的核心要点 + 类型专项（如果匹配到）。
        """
        parts = []
        if self._universal_rules:
            parts.append(f"【创作质量参考标准】\n{self._universal_rules}")
        overlay = self.get_genre_overlay(genre)
        if overlay:
            parts.append(f"\n【类型专项规律】\n{overlay}")
        return "\n".join(parts) if parts else ""

    def reload(self):
        """重新加载 handbook 文件"""
        self.load()

    # ── Loading ──

    def load(self):
        """发现并加载最新版本 handbook"""
        try:
            files = sorted(self.handbook_dir.glob("handbook_v*.md"))
            if not files:
                logger.warning("No handbook files found in %s", self.handbook_dir)
                return
            latest = files[-1]
            # Extract version
            m = re.search(r"v(\d+)", latest.stem)
            self._version = f"v{m.group(1)}" if m else "unknown"

            text = latest.read_text(encoding="utf-8")
            self._raw_text = text
            self._parse(text)
            logger.info("Loaded handbook %s from %s", self._version, latest)
        except Exception as e:
            logger.error("Failed to load handbook: %s", e, exc_info=True)

    def _parse(self, text: str):
        """解析 handbook 为结构化片段"""
        # ── 通用规律：提取第一部分的各维度 Do/Don't 和量化锚点 ──
        universal_section = self._extract_between(text, "## 第一部分：通用规律", "## 第二部分：类型专项")
        if universal_section:
            self._universal_rules = self._extract_dimension_tips(universal_section)

        # ── 类型专项 ──
        genre_section = self._extract_between(text, "## 第二部分：类型专项", "## 第三部分：地雷清单")
        if genre_section:
            self._genre_overlays = self._parse_genre_overlays(genre_section)

        # ── 地雷清单 ──
        red_section = self._extract_between(text, "## 第三部分：地雷清单", "## 第四部分：评分校准刻度")
        if not red_section:
            red_section = self._extract_between(text, "## 第三部分：地雷清单", "## 附录")
        if red_section:
            self._red_flags = self._extract_red_flags(red_section)

    # ── Parsing helpers ──

    @staticmethod
    def _extract_between(text: str, start_marker: str, end_marker: str) -> Optional[str]:
        start = text.find(start_marker)
        if start == -1:
            return None
        start += len(start_marker)
        end = text.find(end_marker, start)
        if end == -1:
            return text[start:]
        return text[start:end].strip()

    @staticmethod
    def _extract_dimension_tips(section: str) -> str:
        """从通用规律部分提取每个维度的量化锚点和可执行建议"""
        tips = []
        # Find each dimension block (supports both Chinese and English parentheses)
        dim_pattern = re.compile(r"## \d+\. \w+\s*[\(（][^）)]+[\)）]\s*\n(.*?)(?=## \d+\. |\Z)", re.DOTALL)
        for m in dim_pattern.finditer(section):
            block = m.group(1)
            # Extract key info: 量化锚点 + 可执行建议
            anchor = ""
            am = re.search(r"\*\*量化锚点\*\*\s*\n(.*?)(?=\n\*\*可执行建议\*\*|\Z)", block, re.DOTALL)
            if am:
                anchor = am.group(1).strip()
            advice = ""
            adm = re.search(r"\*\*可执行建议\*\*\s*\n(.*?)(?=\n\*\*|\Z)", block, re.DOTALL)
            if adm:
                advice = adm.group(1).strip()
            if anchor or advice:
                # Get dimension name (handle Chinese parentheses)
                header_match = re.match(r"## \d+\. (\w+)\s*[\(（]([^）)]+)[\)）]", m.group(0))
                if header_match:
                    dim_name = header_match.group(2).strip()
                    tips.append(f"【{dim_name}】")
                    if anchor:
                        tips.append(f"  {anchor}")
                    if advice:
                        tips.append(f"  {advice}")
                    tips.append("")
        return "\n".join(tips).strip()

    @staticmethod
    def _parse_genre_overlays(section: str) -> dict[str, str]:
        """解析类型专项部分，返回 {类型名: 内容}"""
        overlays = {}
        # Genre headers are like "### 原创 / 萌宝", "### 改编 / 女频", etc.
        # Sub-section headers are like "### 1. 这个类型特别看重什么"
        # Strategy: split by ### then identify genre headers vs numbered sub-headers
        parts = section.split("### ")
        current_genre: Optional[str] = None
        current_parts: list[str] = []

        for part in parts:
            part = part.strip()
            if not part:
                continue
            header_line = part.split("\n", 1)[0].strip()
            # Check if this is a genre header (not a numbered sub-section)
            if not re.match(r"^\d+", header_line):
                # Save previous genre
                if current_genre and current_parts:
                    content = "\n".join(current_parts).strip()
                    if content and "数据不足" not in content:
                        overlays[current_genre] = content
                current_genre = header_line
                current_parts = []
            else:
                # Sub-section of current genre
                if current_genre:
                    current_parts.append(part)

        # Save last genre
        if current_genre and current_parts:
            content = "\n".join(current_parts).strip()
            if content and "数据不足" not in content:
                overlays[current_genre] = content

        return overlays

    @staticmethod
    def _extract_red_flags(section: str) -> str:
        """提取地雷清单，精简为条目列表"""
        flags = []
        # Extract from 高频拒稿原因
        freq = re.search(r"### 一、 高频拒稿原因 TOP \d+\s*\n(.*?)(?=---|\n###)", section, re.DOTALL)
        if freq:
            for line in freq.group(1).strip().split("\n"):
                line = line.strip()
                # Keep numbered items and bold headers
                if re.match(r"^\d+\.", line):
                    flags.append(line)
                elif line.startswith("**") and line.endswith("**"):
                    flags[-1] = flags[-1].replace(line, line.strip("*"))

        # Extract from 致命组合
        fatal = re.search(r"### 二、 致命组合", section, re.DOTALL)
        if fatal:
            block = re.search(r"(.*?)---", fatal.group(), re.DOTALL)
            if block:
                for line in block.group(1).strip().split("\n"):
                    line = line.strip()
                    if line and not line.startswith("###"):
                        flags.append(line)

        # Extract from 一句话地雷清单
        one_liner = re.search(r"### 四、 一句话地雷清单\s*\n(.*?)(?=---|\Z)", section, re.DOTALL)
        if one_liner:
            for line in one_liner.group(1).strip().split("\n"):
                line = line.strip()
                if re.match(r"^\d+\.", line):
                    # Remove leading number
                    line = re.sub(r"^\d+\.\s*", "", line)
                    # Remove "绝对不要" prefix for brevity
                    line = line.replace("绝对不要", "不要")
                    flags.append(line)

        return "\n".join(flags).strip()


# Module-level singleton, loaded on import
_instance: Optional[HandbookProvider] = None


def get_handbook() -> HandbookProvider:
    global _instance
    if _instance is None:
        _instance = HandbookProvider()
    return _instance
