"""
ArchiveMatcher — 对标剧本检索服务
从 script_rubric/outputs/archives 加载评审数据，
按题材关键词 + genre 匹配最相似的高分剧本，格式化为 prompt 注入文本。

触发条件：用户回答 >= 5 轮（问答中后期）
"""
import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 题材关键词词表（从对话历史中匹配特征）
_TOPIC_KEYWORDS = [
    "重生", "穿越", "重来", "逆转", "年代", "古装", "古代", "现代", "都市",
    "民国", "宫廷", "宫斗", "仙侠", "玄幻", "修仙", "末世",
    "萌宝", "孩子", "双胞胎", "婚姻", "闪婚", "离婚", "再婚", "婆媳", "豪门",
    "霸总", "总裁", "家族", "继承", "商战", "职场", "医疗", "律师", "军旅",
    "警察", "娱乐圈", "明星", "创业", "系统", "金手指", "异能", "空间",
    "种田", "美食", "替嫁", "赘婿", "上门", "换亲", "甜宠", "虐恋", "复仇",
    "逆袭", "姐弟", "暗恋", "黑化", "白月光", "竹马", "青梅", "互穿", "双穿",
    "打脸", "报复", "撒糖", "虐", "甜", "宠",
]


class ArchiveMatcher:
    def __init__(self, archives_dir: Optional[str] = None):
        if archives_dir:
            self._dir = Path(archives_dir)
        else:
            _root = Path(__file__).parent.parent.parent.parent
            self._dir = _root / "script_rubric" / "outputs" / "archives"
            if not self._dir.exists():
                self._dir = Path("/app/script_rubric/outputs/archives")
        self._archives: list[dict] = []
        self._load()

    def _load(self):
        self._archives = []
        if not self._dir.exists():
            logger.warning("Archives dir not found: %s", self._dir)
            return
        for f in self._dir.glob("*.json"):
            try:
                d = json.loads(f.read_text("utf-8"))
                if isinstance(d, dict) and d.get("title") and d.get("mean_score") is not None:
                    self._archives.append(d)
            except Exception as e:
                logger.warning("Failed to load archive %s: %s", f.name, e)
        logger.info("ArchiveMatcher loaded %d archives", len(self._archives))

    def extract_keywords(self, history: list[dict]) -> list[str]:
        """从对话历史中提取命中的题材关键词"""
        text = " ".join(m.get("content", "") for m in history)
        return [kw for kw in _TOPIC_KEYWORDS if kw in text]

    def find_benchmarks(
        self,
        genre: str,
        history: list[dict],
        n: int = 2,
    ) -> list[dict]:
        """返回最相关的高分对标剧本（mean_score >= 75）"""
        keywords = self.extract_keywords(history)
        candidates = [a for a in self._archives if (a.get("mean_score") or 0) >= 75]

        def _score(a: dict) -> float:
            s = 0.0
            a_genre = a.get("genre", "")
            # genre 完全匹配
            if genre and a_genre == genre:
                s += 4
            elif genre:
                # 同大类匹配（女频/男频/世情/萌宝）
                for grp in ["女频", "男频", "世情", "萌宝", "改编", "原创"]:
                    if grp in genre and grp in a_genre:
                        s += 2
                        break
            # 关键词在 archive 文本中命中
            a_text = " ".join([
                a.get("title", ""),
                a.get("type_specific_notes", ""),
                " ".join(str(x) for x in a.get("consensus_points", [])),
                " ".join(str(x) for x in a.get("green_flags", [])),
            ])
            for kw in keywords:
                if kw in a_text:
                    s += 1
            # 高分加权
            score_val = a.get("mean_score", 0)
            if score_val >= 78:
                s += 2
            elif score_val >= 76:
                s += 1
            return s

        scored = [(a, _score(a)) for a in candidates]
        scored = [(a, s) for a, s in scored if s > 0]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [a for a, _ in scored[:n]]

    def format_benchmark_context(self, archives: list[dict]) -> str:
        """格式化对标剧本为 prompt 注入文本"""
        if not archives:
            return ""
        lines = [
            "【对标剧本参考——同题材高分校准】",
            "以下为与本剧题材最接近的已评审剧本，请参考其成功要素，同时严格规避其失误。",
        ]
        _status_map = {"签": "已签约", "改": "待改稿", "拒": "已拒稿"}
        for a in archives:
            title = a.get("title", "（未知）")
            genre = a.get("genre", "")
            mean_score = a.get("mean_score", "")
            status_label = _status_map.get(str(a.get("status", "")), str(a.get("status", "")))
            lines.append(f"\n--- 对标：{title}（{genre}，均分 {mean_score}，{status_label}）---")

            green_flags = a.get("green_flags", [])
            if green_flags:
                lines.append("成功要素：" + "；".join(str(g) for g in green_flags))

            red_flags = a.get("red_flags", [])
            if red_flags:
                lines.append("必须规避：" + "；".join(str(r) for r in red_flags))

            notes = a.get("type_specific_notes", "")
            if notes:
                lines.append(f"类型建议：{notes[:150]}{'…' if len(notes) > 150 else ''}")

        lines.append("")
        return "\n".join(lines)

    def reload(self):
        self._load()


_instance: Optional[ArchiveMatcher] = None


def get_archive_matcher() -> ArchiveMatcher:
    global _instance
    if _instance is None:
        _instance = ArchiveMatcher()
    return _instance
