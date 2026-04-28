"""
StyleGuard — 反 AI 味风格管理服务
加载范本样本和金句，提供按 script_type 检索的随机轮换接口。
"""
import json
import logging
import random
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 反 AI 味清单（9 条）
ANTI_SLOP_RULES = """【写作禁忌——绝对不要出现以下内容】
1. 过度抽象形容词（如"眼神中透露出坚毅的目光"）
2. 套路化比喻/暗喻（如"仿佛一把利刃刺穿了心"、"月光如水"）
3. 书面语对白（角色说话要像真人日常对话，不像论文或演讲）
4. 环境描写先行开场（第一镜禁止大空镜/缓慢建立场景/纯旁白开场）
5. 情绪解释代替情绪表现（不要写"她感到很伤心"，写"她眼眶红了，没说话"）
6. 总结性陈词与升华（不要写"这一刻他明白了勇气的真谛"，留白处理）
7. 万能动词"感到/觉得/变得/充满"（用具体阻力动词替代，如"指关节捏得咯吱响"）
8. 排比/三段论（禁止连续三个结构相似的句子或对白）
9. 全知视角心理描写（不要写"他心中泛起一丝苦涩"，用镜头可见的微表情/动作替代）
10. 分屏镜头（禁止出现"画面左右分屏""分屏""一分为二"等分屏描写，所有镜头必须是完整单屏）"""


class StyleGuard:
    """加载 style_samples_{dynamic|explanatory}.json，提供按类型检索的随机范本和金句"""

    def __init__(self, samples_dir: Optional[str] = None):
        if samples_dir:
            self.samples_dir = Path(samples_dir)
        else:
            # __file__ → backend/app/services/style_guard.py
            # .parent → services, .parent → app, .parent → backend, .parent → project root
            _root = Path(__file__).parent.parent.parent.parent
            self.samples_dir = _root / "script_rubric" / "outputs"
            # Fallback for Docker
            if not self.samples_dir.exists():
                self.samples_dir = Path("/app/script_rubric/outputs")

        self._dynamic_data: Optional[dict] = None
        self._explanatory_data: Optional[dict] = None
        self._load()

    # ── Public ──

    def get_style_samples(
        self,
        script_type: str,
        count: int = 1,
        genre: Optional[str] = None,
    ) -> list[dict]:
        """按 script_type 抽样，同 genre 优先，不足则回退同 script_type 全池。

        返回 list[dict]，每条含 title/excerpt/genre/theme_tag。
        """
        data = self._get_data(script_type)
        if not data:
            return []
        all_samples = data.get("samples", []) or []
        if not all_samples:
            return []

        # Prefer same-genre subset
        pool = all_samples
        if genre:
            same_genre = [s for s in all_samples if isinstance(s, dict) and s.get("genre") == genre]
            if same_genre:
                pool = same_genre

        n = min(count, len(pool))
        picked = random.sample(pool, n)

        # Top up from full pool if genre subset too small to meet count
        if len(picked) < count:
            remaining = [s for s in all_samples if s not in picked]
            extra = random.sample(remaining, min(count - len(picked), len(remaining)))
            picked.extend(extra)

        # Normalize old string-only entries to dict format (defensive)
        normalized = []
        for p in picked:
            if isinstance(p, dict):
                normalized.append(p)
            else:
                normalized.append({"title": "", "excerpt": str(p), "genre": "", "theme_tag": ""})
        return normalized

    def get_golden_quotes(self, script_type: str) -> list[str]:
        """返回金句/句式列表"""
        data = self._get_data(script_type)
        if not data:
            return []
        return data.get("golden_quotes", [])

    def get_anti_slop_rules(self) -> str:
        """返回 9 条反 AI 味清单，格式化为 prompt 文本"""
        return ANTI_SLOP_RULES

    def build_style_context(
        self,
        script_type: str,
        genre: Optional[str] = None,
    ) -> str:
        """组合：范本 + 金句 → <examples> 标签块。同 genre 优先。"""
        samples = self.get_style_samples(script_type, count=2, genre=genre)
        quotes = self.get_golden_quotes(script_type)
        if not samples and not quotes:
            return ""

        parts = [
            "【风格参考范本】",
            "以下是编辑认可的高分剧本片段，请模仿其节奏、句式结构和对白口吻。",
            "严禁直接使用范本中的具体辞藻、人名、地名。",
            "",
            "<examples>",
        ]

        for s in samples:
            title = s.get("title", "")
            excerpt = s.get("excerpt", "")
            if title:
                parts.append(f"── {title} ──")
            parts.append(excerpt)
            parts.append("")

        if quotes:
            parts.append("--- 金句/句式参考 ---")
            for q in quotes:
                parts.append(q)

        parts.append("</examples>")
        return "\n".join(parts)

    def reload(self):
        """重新加载样本文件"""
        self._load()

    # ── Private ──

    def _load(self):
        """加载动态漫和解说漫的样本 JSON"""
        self._dynamic_data = self._load_file("style_samples_dynamic.json")
        self._explanatory_data = self._load_file("style_samples_explanatory.json")

    def _load_file(self, filename: str) -> Optional[dict]:
        """加载单个 JSON 样本文件"""
        filepath = self.samples_dir / filename
        if not filepath.exists():
            logger.warning("Style samples file not found: %s", filepath)
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
            logger.info("Loaded style samples: %s", filename)
            return data
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load style samples %s: %s", filename, e)
            return None

    def _get_data(self, script_type: str) -> Optional[dict]:
        """根据 script_type 返回对应的样本数据"""
        if script_type == "explanatory":
            return self._explanatory_data
        # dynamic 为默认值
        return self._dynamic_data


# Module-level singleton
_instance: Optional[StyleGuard] = None


def get_style_guard() -> StyleGuard:
    global _instance
    if _instance is None:
        _instance = StyleGuard()
    return _instance
