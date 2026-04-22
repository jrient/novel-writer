# Episode Content 去 AI 味 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将真实高分剧本的范文笔样本 + 金句 + 反 AI 味清单注入 `generate_episode_content` prompt，消除生成内容的"AI 味"。

**Architecture:** 三层注入架构 — System prompt 追加反例清单，User prompt 末尾追加 `<examples>` 范本+金句。范本由独立的提取脚本从 rubric 数据中生成 JSON，由 StyleGuard 服务加载并随机轮换。

**Tech Stack:** Python 3, httpx, FastAPI, pytest

---

### Task 1: 编写范本提取脚本并生成 JSON 数据

**Files:**
- Create: `script_rubric/pipeline/extract_fewshots.py`
- Create: `script_rubric/outputs/style_samples_dynamic.json`
- Create: `script_rubric/outputs/style_samples_explanatory.json`

**背景数据（已核实）：**

- rubric 中有 10 部 status=签 且 writing_dialogue≥7 的剧本，但 text_content 多为人设+大纲+前三集混合体
- `drama/动态漫：皇子.txt` — 完整分场剧本，59 集，格式规范（△动作/对白/VO/OS）
- `drama/解说漫：买榴莲.txt` — 解说漫小说体，第一人称，233 段

**步骤：**

- [ ] **Step 1: 编写 extract_fewshots.py 脚本**

```python
#!/usr/bin/env python3
"""
extract_fewshots.py — 从 rubric 数据中提风格范本和金句
输出 style_samples_dynamic.json 和 style_samples_explanatory.json
"""
import json
import random
import re
from pathlib import Path

# 项目根目录（脚本在 script_rubric/pipeline/）
PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_JSON = PROJECT_ROOT / "script_rubric" / "data" / "parsed" / "scripts.json"
ARCHIVES_DIR = PROJECT_ROOT / "script_rubric" / "outputs" / "archives"
OUTPUT_DIR = PROJECT_ROOT / "script_rubric" / "outputs"


def load_qualified_scripts():
    """
    加载 qualified 剧本（status=签 且 writing_dialogue≥7）
    从 archive 文件获取维度评分，从 scripts.json 获取原文
    """
    # 1. 从 archive 获取 qualified titles
    archives = {}
    for f in ARCHIVES_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            dims = d.get("dimensions", {})
            if not isinstance(dims, dict):
                continue
            wd = dims.get("writing_dialogue", {}).get("score", 0)
            if wd >= 7 and d.get("status") == "签":
                archives[d["title"]] = {
                    "mean_score": d.get("mean_score", 0),
                    "writing_dialogue": wd,
                    "title": d["title"],
                }
        except (json.JSONDecodeError, KeyError):
            continue

    # 2. 从 scripts.json 获取 text_content
    scripts = json.loads(SCRIPTS_JSON.read_text(encoding="utf-8"))
    qualified = []
    for s in scripts:
        title = s["title"]
        if title in archives:
            text = s.get("text_content") or ""
            if len(text) > 200:
                archives[title]["text_content"] = text
                qualified.append(archives[title])

    qualified.sort(key=lambda x: -x["mean_score"])
    return qualified


def extract_dynamic_sample(text: str) -> str:
    """
    从混合文本中提取分场正文（△动作/对白格式）
    策略：找到第一个 "第N集" 或场次号（如 "01-1"）后的内容，
    取第一个场景的完整片段，截断到 400-500 字
    """
    # 匹配分场行：如 "01-1 京城大学堂 日/内"
    scene_pattern = re.compile(r"^\d{2}-\d+[\s　].*$", re.MULTILINE)
    matches = list(scene_pattern.finditer(text))
    if not matches:
        # 尝试匹配 "第N集"
        ep_pattern = re.compile(r"^第\d+集[：:]*$", re.MULTILINE)
        matches = list(ep_pattern.finditer(text))

    if matches:
        # 从第一个分场开始取 400 字
        start = matches[0].start()
        excerpt = text[start:start + 500].strip()
        # 在完整行边界截断
        newline = excerpt.rfind("\n")
        if newline > 300:
            excerpt = excerpt[:newline].strip()
        return excerpt

    # 兜底：取前 500 字
    return text[:500].strip()


def build_dynamic_json(scripts: list[dict]) -> dict:
    """构建动态漫 style_samples_dynamic.json"""
    samples = []
    for s in scripts:
        text = s.get("text_content", "")
        excerpt = extract_dynamic_sample(text)
        if len(excerpt) > 100:
            samples.append({
                "title": s["title"],
                "mean_score": s.get("mean_score", 0),
                "writing_dialogue_score": s.get("writing_dialogue", 0),
                "excerpt": excerpt,
            })

    # 从 drama/动态漫：皇子.txt 提取金句（格式规范的分场剧本）
    prince_file = PROJECT_ROOT / "drama" / "动态漫：皇子.txt"
    prince_quotes = extract_prince_quotes(prince_file)

    # 从 archive evidence 中提取高分金句
    archive_quotes = extract_archive_quotes(scripts)

    golden_quotes = prince_quotes + archive_quotes

    return {
        "script_type": "dynamic",
        "samples": samples,
        "golden_quotes": golden_quotes,
    }


def extract_prince_quotes(file_path: Path) -> list[str]:
    """从《皇子》分场剧本提取金句/句式"""
    if not file_path.exists():
        return []
    text = file_path.read_text(encoding="utf-8")
    quotes = []
    # 提取 △ 动作行（简洁有力的）
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("△") and 10 < len(line) < 60:
            # 过滤含角色说明的行（含括号说明）
            if "：" not in line or line.count("：") == 1:
                quotes.append(line)
    # 提取带情绪标签的对白
    for line in text.split("\n"):
        line = line.strip()
        # 角色名（情绪）：对白
        if re.search(r"[（(].{1,6}[）)]\s*：", line) and 15 < len(line) < 80:
            quotes.append(line)
    # 去重，限制数量
    seen = set()
    unique = []
    for q in quotes:
        if q not in seen:
            seen.add(q)
            unique.append(q)
    return unique[:20]


def extract_archive_quotes(scripts: list[dict]) -> list[str]:
    """从 rubric 的 archives 中提取 writing_dialogue evidence"""
    quotes = []
    for s in scripts:
        title = s["title"]
        archive_file = ARCHIVES_DIR / f"{title}.json"
        if archive_file.exists():
            try:
                d = json.loads(archive_file.read_text(encoding="utf-8"))
                dims = d.get("dimensions", {})
                wd = dims.get("writing_dialogue", {})
                for ev in wd.get("evidence_from_text", []):
                    # evidence 可能包含完整场景引用，只取对白行
                    if len(ev) < 100:
                        quotes.append(ev)
            except (json.JSONDecodeError, KeyError):
                pass
    return quotes[:10]


def build_explanatory_json() -> dict:
    """
    构建解说漫 style_samples_explanatory.json
    唯一范本：drama/解说漫：买榴莲.txt
    """
    file_path = PROJECT_ROOT / "drama" / "解说漫：买榴莲.txt"
    if not file_path.exists():
        return {"script_type": "explanatory", "samples": [], "golden_quotes": []}

    text = file_path.read_text(encoding="utf-8")

    # 提取开场场景（第 1 节的前 400 字）
    # 找到第一个 "1\n" 之后的内容
    start = text.find("\n1\n")
    if start == -1:
        start = 0
    else:
        start += 3  # skip "\n1\n"

    excerpt = text[start:start + 450].strip()
    # 在行边界截断
    newline = excerpt.rfind("\n")
    if newline > 300:
        excerpt = excerpt[:newline].strip()

    # 手工提炼金句/句式
    golden_quotes = [
        "快递员敲门的时候，我正烧得浑身骨头缝都在疼。",
        "艰难地裹着羽绒服，扶着墙挪到玄关。",
        "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
        "我胃里一阵翻江倒海，猛地捂住嘴。",
        "我扶着门框的手指骨节泛白，指甲死死抠进木头里。",
        "字字句句，像淬了毒的针，扎进我高烧脆弱的神经里。",
        "我冷冷地看着这对父子。",
        "高烧让我浑身发冷，心却比这温度更冷。",
        "哀莫大于心死。原来就是这种感觉。",
        "没有愤怒的咆哮，没有歇斯底里的哭喊。只有一种极其清晰的、冷彻骨髓的平静。",
        "嘴角勾起一抹极其温柔的笑。",
        "他是个程序员，那台一万多的外星人电脑是他的命根子。",
        "他咒骂了一句，转身缩回了主卧。",
        "深夜。万籁俱寂。只有冰柜压缩机运转的嗡嗡声。",
        "我的手指已经被坚硬的榴莲壳磨出了血泡。",
        "动作单调，重复。",
    ]

    return {
        "script_type": "explanatory",
        "samples": [
            {
                "title": "解说漫：买榴莲",
                "excerpt": excerpt,
            }
        ],
        "golden_quotes": golden_quotes,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 动态漫
    scripts = load_qualified_scripts()
    print(f"Found {len(scripts)} qualified scripts")
    dynamic_json = build_dynamic_json(scripts)
    output_dynamic = OUTPUT_DIR / "style_samples_dynamic.json"
    output_dynamic.write_text(
        json.dumps(dynamic_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {output_dynamic}")

    # 解说漫
    explanatory_json = build_explanatory_json()
    output_explanatory = OUTPUT_DIR / "style_samples_explanatory.json"
    output_explanatory.write_text(
        json.dumps(explanatory_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {output_explanatory}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行脚本生成 JSON**

```bash
cd /data/project/novel-writer
python script_rubric/pipeline/extract_fewshots.py
```

Expected: 输出 `style_samples_dynamic.json` 和 `style_samples_explanatory.json`

- [ ] **Step 3: 验证输出内容**

```bash
python3 -c "
import json
for f in ['style_samples_dynamic.json', 'style_samples_explanatory.json']:
    d = json.load(open(f'script_rubric/outputs/{f}'))
    print(f'{f}: {len(d[\"samples\"])} samples, {len(d[\"golden_quotes\"])} quotes')
    if d['samples']:
        print(f'  First sample: {d[\"samples\"][0][\"title\"]} ({len(d[\"samples\"][0][\"excerpt\"])} chars)')
"
```

Expected: 动态漫 ≥1 samples + ≥10 quotes, 解说漫 ≥1 samples + ≥10 quotes

- [ ] **Step 4: Commit**

```bash
git add script_rubric/pipeline/extract_fewshots.py script_rubric/outputs/style_samples_*.json
git commit -m "feat: add style sample extraction script and initial dynamic/explanatory samples"
```

---

### Task 2: 编写 StyleGuard 服务 + 单元测试

**Files:**
- Create: `backend/app/services/style_guard.py`
- Create: `backend/tests/test_style_guard.py`

- [ ] **Step 1: 编写 failing test**

```python
# backend/tests/test_style_guard.py
"""StyleGuard 服务单元测试"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def sample_dir(tmp_path):
    """创建临时样本目录"""
    dynamic_samples = {
        "script_type": "dynamic",
        "samples": [
            {"title": "剧本A", "excerpt": "△张总猛拍桌，文件飞散。"},
            {"title": "剧本B", "excerpt": "△李秘书推门而入，脸色铁青。"},
            {"title": "剧本C", "excerpt": "△王老板摔门而去，茶杯震翻在地。"},
        ],
        "golden_quotes": [
            "张总（暴怒）：三十万！你敢说不知道？！",
            "△李秘书冷笑一声，把文件甩在桌上。",
            "王老板（颤抖）：我……我以为你会懂。",
            "△她眼眶红了，没说话。",
        ],
    }
    explanatory_samples = {
        "script_type": "explanatory",
        "samples": [
            {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。"},
        ],
        "golden_quotes": [
            "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
            "我扶着门框的手指骨节泛白，指甲死死抠进木头里。",
        ],
    }
    (tmp_path / "style_samples_dynamic.json").write_text(
        json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "style_samples_explanatory.json").write_text(
        json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_style_guard_loads_dynamic_samples(sample_dir):
    """StyleGuard 加载动态漫范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic")
    assert len(samples) == 1  # 默认返回 1 段
    assert isinstance(samples[0], str)
    assert len(samples[0]) > 0


def test_style_guard_loads_explanatory_samples(sample_dir):
    """StyleGuard 加载解说漫范本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("explanatory")
    assert len(samples) == 1
    assert isinstance(samples[0], str)


def test_style_guard_random_rotation(sample_dir):
    """get_style_samples(count=2) 随机返回不同样本"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    # 多次调用，验证不是每次都返回相同组合
    results = set()
    for _ in range(10):
        samples = sg.get_style_samples("dynamic", count=2)
        results.add(tuple(samples))
    # 至少有 2 种不同组合（随机性）
    assert len(results) >= 2


def test_style_guard_returns_all_when_count_exceeds(sample_dir):
    """count 超过样本数时返回全部"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("dynamic", count=10)
    assert len(samples) == 3  # 只有 3 段样本


def test_style_guard_get_golden_quotes(sample_dir):
    """get_golden_quotes 返回金句列表"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    quotes = sg.get_golden_quotes("dynamic")
    assert len(quotes) > 0
    assert isinstance(quotes, list)
    # 所有金句都是字符串
    assert all(isinstance(q, str) for q in quotes)


def test_style_guard_get_anti_slop_rules():
    """get_anti_slop_rules 返回 9 条反 AI 味清单"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard()
    rules = sg.get_anti_slop_rules()
    assert isinstance(rules, str)
    assert len(rules) > 100
    # 验证包含关键条目
    assert "比喻" in rules or "暗喻" in rules
    assert "情绪" in rules


def test_style_guard_build_style_context(sample_dir):
    """build_style_context 组合范本+金句为 <examples> 块"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    context = sg.build_style_context("dynamic")
    assert "<examples>" in context
    assert "</examples>" in context
    assert "节奏" in context or "句式" in context  # 包含引导语


def test_style_guard_missing_file(sample_dir):
    """不存在的 script_type 返回空上下文"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard(samples_dir=str(sample_dir))
    samples = sg.get_style_samples("unknown_type")
    assert samples == []
    quotes = sg.get_golden_quotes("unknown_type")
    assert quotes == []


def test_style_guard_default_dir_not_crash():
    """使用默认目录且文件不存在时不崩溃"""
    from app.services.style_guard import StyleGuard
    sg = StyleGuard()
    samples = sg.get_style_samples("dynamic")
    assert isinstance(samples, list)
    quotes = sg.get_golden_quotes("dynamic")
    assert isinstance(quotes, list)
    rules = sg.get_anti_slop_rules()
    assert isinstance(rules, str)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_style_guard.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.style_guard'"

- [ ] **Step 3: Write StyleGuard implementation**

```python
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
9. 全知视角心理描写（不要写"他心中泛起一丝苦涩"，用镜头可见的微表情/动作替代）"""


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

    def get_style_samples(self, script_type: str, count: int = 1) -> list[str]:
        """随机返回 1-N 段范本（轮换防固化）"""
        data = self._get_data(script_type)
        if not data:
            return []
        samples = data.get("samples", [])
        if not samples:
            return []
        count = min(count, len(samples))
        return random.sample(samples, count)

    def get_golden_quotes(self, script_type: str) -> list[str]:
        """返回金句/句式列表"""
        data = self._get_data(script_type)
        if not data:
            return []
        return data.get("golden_quotes", [])

    def get_anti_slop_rules(self) -> str:
        """返回 9 条反 AI 味清单，格式化为 prompt 文本"""
        return ANTI_SLOP_RULES

    def build_style_context(self, script_type: str) -> str:
        """组合：范本 + 金句，格式化为 <examples> 标签块"""
        samples = self.get_style_samples(script_type)
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
            excerpt = s.get("excerpt", "") if isinstance(s, dict) else str(s)
            title = s.get("title", "") if isinstance(s, dict) else ""
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_style_guard.py -v
```

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/style_guard.py backend/tests/test_style_guard.py
git commit -m "feat: add StyleGuard service for anti-AI sloppiness style management"
```

---

### Task 3: 修改 `script_ai_service.py` 的 `generate_episode_content` prompt

**Files:**
- Modify: `backend/app/services/script_ai_service.py`

- [ ] **Step 1: 在 `_get_prompts` 下方新增反 AI 味注入方法**

在 `_get_prompts` 函数之后、`calc_outline_max_tokens` 之前，新增一个 helper 函数（或在 ScriptAIService 类中添加方法）：

```python
def _build_episode_system_prompt(
    base_system: str,
    script_type: str,
) -> str:
    """
    为 episode_content 构建三层 system prompt：
    1. 原始规则（base_system）
    2. 反 AI 味清单（追加到末尾）
    """
    from app.services.style_guard import get_style_guard

    sg = get_style_guard()
    anti_slop = sg.get_anti_slop_rules()
    if anti_slop:
        return f"{base_system}\n\n{anti_slop}"
    return base_system


def _build_episode_user_prompt(
    base_user: str,
    script_type: str,
) -> str:
    """
    为 episode_content 构建三层 user prompt：
    1. 原始生成指令（base_user）
    2. <examples> 范本+金句（追加到末尾）
    """
    from app.services.style_guard import get_style_guard

    sg = get_style_guard()
    style_ctx = sg.build_style_context(script_type)
    if style_ctx:
        return f"{base_user}\n\n{style_ctx}"
    return base_user
```

- [ ] **Step 2: 修改 `generate_episode_content` 方法**

找到 `generate_episode_content` 方法（约第 663 行），修改 prompt 构建部分：

修改前：
```python
prompt = prompt_entry["user"].format(**format_kwargs)
system_prompt = prompt_entry["system"]
messages = self._build_messages(prompt, system_prompt)
```

修改后：
```python
prompt = prompt_entry["user"].format(**format_kwargs)
system_prompt = prompt_entry["system"]

# 注入反 AI 味清单到 system prompt
system_prompt = _build_episode_system_prompt(system_prompt, script_type)

# 注入范本+金句到 user prompt
prompt = _build_episode_user_prompt(prompt, script_type)

messages = self._build_messages(prompt, system_prompt)
```

- [ ] **Step 3: 修改解说漫的 `_get_system_prompt` 方法**

解说漫的 `episode_content` system prompt 也需要同样注入反 AI 味清单。由于 `_build_episode_system_prompt` 已经处理了这个逻辑，需要确保 `generate_episode_content` 对两种 script_type 都调用它。

确认 `generate_episode_content` 中的 `_get_prompts(script_type)` 已正确返回对应类型的 prompt，然后追加注入。

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/script_ai_service.py
git commit -m "feat: inject anti-AI sloppiness rules and style samples into episode_content prompt"
```

---

### Task 4: 更新剧本 AI 服务测试 + 反 AI 味集成测试

**Files:**
- Modify: `backend/tests/test_drama_ai_service.py`
- Create: `backend/tests/test_episode_content_prompt.py`

- [ ] **Step 1: 新增 episode_content prompt 集成测试**

```python
# backend/tests/test_episode_content_prompt.py
"""
Episode content prompt 三层结构集成测试
验证反 AI 味清单和范本注入正确工作
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def style_samples_dir(tmp_path):
    """创建测试用样本目录"""
    dynamic_samples = {
        "script_type": "dynamic",
        "samples": [
            {"title": "剧本A", "excerpt": "△张总猛拍桌，文件飞散。\n张总（暴怒）：三十万！公司账上的三十万！"},
        ],
        "golden_quotes": [
            "△她眼眶红了，没说话。",
            "张总（暴怒）：三十万！你敢说不知道？！",
        ],
    }
    explanatory_samples = {
        "script_type": "explanatory",
        "samples": [
            {"title": "买榴莲", "excerpt": "快递员敲门的时候，我正烧得浑身骨头缝都在疼。"},
        ],
        "golden_quotes": [
            "门刚拉开一条缝。一股浓烈到令人作呕的味道，瞬间冲进鼻腔。",
        ],
    }
    (tmp_path / "style_samples_dynamic.json").write_text(
        json.dumps(dynamic_samples, ensure_ascii=False), encoding="utf-8"
    )
    (tmp_path / "style_samples_explanatory.json").write_text(
        json.dumps(explanatory_samples, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


class TestAntiSlopInjection:
    """反 AI 味清单注入测试"""

    def test_anti_slop_rules_in_system_prompt(self, style_samples_dir):
        """system prompt 包含反 AI 味清单"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(style_samples_dir))
        rules = sg.get_anti_slop_rules()

        assert "写作禁忌" in rules
        assert "比喻" in rules or "暗喻" in rules
        assert "情绪" in rules
        assert "万能动词" in rules or "感到" in rules
        assert "排比" in rules
        assert "心理描写" in rules

    def test_anti_slop_rules_count(self):
        """反 AI 味清单有 9 条"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard()
        rules = sg.get_anti_slop_rules()
        # Count numbered items
        import re
        items = re.findall(r"^\d+\.", rules, re.MULTILINE)
        assert len(items) == 9


class TestStyleContextInjection:
    """范本+金句注入测试"""

    def test_build_style_context_contains_examples(self, style_samples_dir):
        """build_style_context 返回包含范本和金句的 <examples> 块"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(style_samples_dir))
        ctx = sg.build_style_context("dynamic")

        assert "<examples>" in ctx
        assert "</examples>" in ctx
        assert "剧本A" in ctx
        assert "张总猛拍桌" in ctx
        assert "金句" in ctx or "参考" in ctx
        assert "节奏" in ctx or "句式" in ctx  # 引导语

    def test_build_style_context_explanatory(self, style_samples_dir):
        """解说漫 build_style_context 返回正确内容"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(style_samples_dir))
        ctx = sg.build_style_context("explanatory")

        assert "<examples>" in ctx
        assert "买榴莲" in ctx
        assert "快递员敲门" in ctx

    def test_build_style_context_empty_for_missing_type(self, style_samples_dir):
        """不存在的 script_type 返回空字符串"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir=str(style_samples_dir))
        ctx = sg.build_style_context("unknown")
        assert ctx == ""

    def test_build_style_context_without_files(self):
        """没有样本文件时 build_style_context 返回空字符串"""
        from app.services.style_guard import StyleGuard

        sg = StyleGuard(samples_dir="/nonexistent/path")
        ctx = sg.build_style_context("dynamic")
        assert ctx == ""


class TestPromptStructure:
    """Prompt 结构验证测试"""

    def test_dynamic_episode_prompt_has_all_layers(self):
        """动态漫 episode_content prompt 包含规则层"""
        from app.services.script_ai_service import EXPLANATORY_PROMPTS, DYNAMIC_PROMPTS

        sys_prompt = DYNAMIC_PROMPTS["episode_content"]["system"]
        user_prompt = DYNAMIC_PROMPTS["episode_content"]["user"]

        # 规则层必须存在
        assert len(sys_prompt) > 50
        assert len(user_prompt) > 100

    def test_explanatory_episode_prompt_has_format(self):
        """解说漫 episode_content prompt 包含格式要求"""
        from app.services.script_ai_service import EXPLANATORY_PROMPTS

        sys_prompt = EXPLANATORY_PROMPTS["episode_content"]["system"]
        user_prompt = EXPLANATORY_PROMPTS["episode_content"]["user"]

        assert "△" in user_prompt  # 动作标记
        assert "{episode_number}-1" in user_prompt  # 分场号格式
```

- [ ] **Step 2: Run all drama AI service tests**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/test_drama_ai_service.py tests/test_style_guard.py tests/test_episode_content_prompt.py -v
```

Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_drama_ai_service.py backend/tests/test_episode_content_prompt.py
git commit -m "test: add integration tests for episode content anti-AI prompt injection"
```

---

### Task 5: 端到端验证 + 最终确认

**Files:** 无新增文件

- [ ] **Step 1: 运行全量测试**

```bash
cd /data/project/novel-writer/backend
python -m pytest tests/ -v -k "drama or style or episode" --tb=short
```

- [ ] **Step 2: 验证 import 不崩溃**

```bash
cd /data/project/novel-writer/backend
python -c "
from app.services.style_guard import StyleGuard, get_style_guard
sg = get_style_guard()
print('StyleGuard loaded:', sg.version if hasattr(sg, 'version') else 'OK')
print('Anti-slop rules:', len(sg.get_anti_slop_rules()))
print('Dynamic samples:', len(sg.get_style_samples('dynamic')))
print('Dynamic quotes:', len(sg.get_golden_quotes('dynamic')))
print('Style context (first 100 chars):', sg.build_style_context('dynamic')[:100])
"
```

- [ ] **Step 3: 验证 script_ai_service 正常加载**

```bash
cd /data/project/novel-writer/backend
python -c "
from app.services.script_ai_service import ScriptAIService
svc = ScriptAIService()
print('ScriptAIService loaded OK')
print('Provider:', svc.provider)
print('Model:', svc.model)
"
```

- [ ] **Step 4: 最终 Commit（如有额外变更）**

```bash
git status
# 如果有未提交的文件:
git add -A
git commit -m "chore: final verification cleanup"
```
