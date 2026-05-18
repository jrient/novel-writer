"""
HandbookProvider — 加载并解析剧本评审手册（handbook_vN.md）
将 markdown 解析为结构化片段，按阶段/类型提供裁剪后的文本。
"""
import logging
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 30  # 每 30 秒检查一次是否有新版本


class HandbookProvider:
    """从 handbook 文件加载知识，提供按类型检索的片段"""

    def __init__(self, handbook_dir: Optional[str] = None):
        if handbook_dir:
            self.handbook_dir = Path(handbook_dir)
        else:
            # __file__ → backend/app/services/handbook_provider.py
            # .parent → services, .parent → app, .parent → backend, .parent → project root
            # Then: project_root/script_rubric/outputs/handbook
            _root = Path(__file__).parent.parent.parent.parent
            self.handbook_dir = _root / "script_rubric" / "outputs" / "handbook"
            # Fallback: if running inside Docker with /app as project root
            if not self.handbook_dir.exists():
                self.handbook_dir = Path("/app/script_rubric/outputs/handbook")
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
            files = sorted(self.handbook_dir.glob("handbook_v*.md"),
                           key=lambda f: int(re.search(r"v(\d+)", f.stem).group(1)))
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
        """从通用规律部分提取每个维度的量化锚点和可执行建议。

        兼容两种 handbook 维度标题格式：
        - v10: `## 1. Word (中文名)`     —— level-2，单词英文
        - v14: `### 1. Word Word（中文名）` —— level-3，多词英文，全角括号
        """
        tips = []
        # 维度标题：## 或 ###；编号；英文（可能多词，含空格 & 字符）；中文括号（半角/全角）
        dim_pattern = re.compile(
            r"#{2,3} \d+\. [A-Za-z][\w &/]*\s*[\(（][^）)]+[\)）]\s*\n(.*?)(?=#{2,3} \d+\. [A-Za-z]|\Z)",
            re.DOTALL,
        )
        header_re = re.compile(r"#{2,3} \d+\. [\w &/]+\s*[\(（]([^）)]+)[\)）]")
        for m in dim_pattern.finditer(section):
            block = m.group(1)
            anchor = ""
            am = re.search(r"\*\*量化锚点[:：]?\*\*\s*\n(.*?)(?=\n\*\*可执行建议[:：]?\*\*|\Z)", block, re.DOTALL)
            if am:
                anchor = am.group(1).strip()
            advice = ""
            adm = re.search(r"\*\*可执行建议[:：]?\*\*\s*\n(.*?)(?=\n\*\*|\Z)", block, re.DOTALL)
            if adm:
                advice = adm.group(1).strip()
            if anchor or advice:
                header_match = header_re.match(m.group(0))
                if header_match:
                    dim_name = header_match.group(1).strip()
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
        """提取地雷清单，精简为条目列表。

        兼容两种 handbook 子标题格式：
        - v10: `### 🏆 一、 高频拒稿原因 TOP N`、`### 二、 致命组合`、`### 四、 一句话地雷清单`
        - v14: `### 1. 高频拒稿原因 TOP N`、`### 2. 致命组合`（无"一句话地雷清单"小节）
        """
        flags: list[str] = []

        # ── 高频拒稿原因 ─────────────────────────────────────────
        # 兼容："### 🏆 一、 高频拒稿原因 TOP 10" / "### 1. 高频拒稿原因 TOP 10"
        freq = re.search(
            r"###\s*(?:[^\n]*?(?:一、|1\.))\s*高频拒稿原因\s*TOP\s*\d+[^\n]*\n(.*?)(?=\n---|\n### |\Z)",
            section,
            re.DOTALL,
        )
        if freq:
            # 提取 **N. xxx**  形式的粗体编号行；同时兼容裸 "1. xxx" 行
            for raw in freq.group(1).split("\n"):
                line = raw.strip()
                if not line:
                    continue
                # 粗体编号行："**3. 反派降智...**"
                m = re.match(r"^\*\*(\d+\.\s*.+?)\*\*\s*$", line)
                if m:
                    flags.append(m.group(1).strip())
                    continue
                # 兼容裸编号行（v10 旧排版）："1. xxx"
                if re.match(r"^\d+\.\s+", line) and not line.startswith("*"):
                    flags.append(line)

        # ── 致命组合 ─────────────────────────────────────────────
        fatal = re.search(
            r"###\s*(?:[^\n]*?(?:二、|2\.))\s*致命组合[^\n]*\n(.*?)(?=\n---|\n### |\Z)",
            section,
            re.DOTALL,
        )
        if fatal:
            # 提取 "**💣 致命组合一：xxx（原理）**" 形式的粗体标题行
            for raw in fatal.group(1).split("\n"):
                line = raw.strip()
                if not line.startswith("**") or not line.endswith("**"):
                    continue
                stripped = line.strip("*").strip()
                if stripped:
                    flags.append(stripped)

        # ── 一句话地雷清单（v10 才有，v14 已合并到高频拒稿） ─────
        one_liner = re.search(
            r"###\s*(?:[^\n]*?(?:四、|4\.))\s*一句话地雷清单\s*\n(.*?)(?=\n---|\n### |\Z)",
            section,
            re.DOTALL,
        )
        if one_liner:
            for raw in one_liner.group(1).split("\n"):
                line = raw.strip()
                if re.match(r"^\d+\.", line):
                    line = re.sub(r"^\d+\.\s*", "", line).replace("绝对不要", "不要")
                    flags.append(line)

        return "\n".join(flags).strip()


def build_handbook_red_flags_block(genre: Optional[str] = None) -> str:
    """构造可注入 writing/rewriting prompt 的 handbook 片段（红线 + 可选类型专项）。

    - 当 handbook 已加载：返回带版本标注的负向约束块
    - 当 handbook 未加载或解析为空：返回空串（调用方应优雅降级）

    设计取向：只注入"必须避免的红线"和"类型专项"，**不注入** universal_rules
    （那是描述性规律，注入到生成 prompt 会让模型困惑）。
    """
    hb = get_handbook()
    parts: list[str] = []
    red = hb.get_red_flags()
    if red:
        parts.append(
            f"【评审手册 {hb.version} · 必须避免的红线/雷点】\n{red}"
        )
    if genre:
        overlay = hb.get_genre_overlay(genre)
        if overlay:
            parts.append(
                f"【评审手册 {hb.version} · 类型专项 · {genre}】\n{overlay}"
            )
    return "\n\n".join(parts)


# Module-level singleton, loaded on import
_instance: Optional[HandbookProvider] = None
_last_check_time: float = 0


def get_handbook() -> HandbookProvider:
    global _instance, _last_check_time
    if _instance is None:
        _instance = HandbookProvider()
        _last_check_time = time.time()
        return _instance

    # 每 _CHECK_INTERVAL 秒检查一次是否有新版本
    now = time.time()
    if now - _last_check_time > _CHECK_INTERVAL:
        _last_check_time = now
        files = sorted(_instance.handbook_dir.glob("handbook_v*.md"),
                       key=lambda f: int(re.search(r"v(\d+)", f.stem).group(1)))
        if files:
            m = re.search(r"v(\d+)", files[-1].stem)
            latest_version = f"v{m.group(1)}" if m else "unknown"
            if latest_version != _instance._version:
                logger.info(f"Auto-reloading handbook: {_instance._version} -> {latest_version}")
                _instance.reload()

    return _instance
